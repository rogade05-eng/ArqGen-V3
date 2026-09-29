/*
 * Separate experimental Windows/browser launcher, NOT the Tauri shell.
 * The generated embedded_assets.h contains only the Vite build and its WASM.
 * The server has no APIs: it serves a fixed read-only allowlist on 127.0.0.1.
 * Compile the same HTTP implementation for Linux smoke tests, then with Zig
 * for Windows x64. This is not native WebView2 QA or an architectural product.
 */
#define _POSIX_C_SOURCE 200809L
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <shellapi.h>
typedef SOCKET server_socket;
#define CLOSE_SOCKET closesocket
#else
#include <arpa/inet.h>
#include <netinet/in.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>
typedef int server_socket;
#define INVALID_SOCKET (-1)
#define SOCKET_ERROR (-1)
#define CLOSE_SOCKET close
#endif
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "embedded_assets.h"

#define APP_PORT 48765
#define MAX_REQUEST 8192
static server_socket listener = INVALID_SOCKET;
#ifdef _WIN32
static volatile LONG running = 1;
static HANDLE server_thread_handle = NULL;
static wchar_t browser_url[96];
#else
static volatile sig_atomic_t running = 1;
#endif

static int send_all(server_socket socket, const void *data, size_t size) {
  const char *bytes = (const char *)data;
  while (size) {
    int amount = size > 32768 ? 32768 : (int)size;
    int written = send(socket, bytes, amount, 0);
    if (written <= 0) return 0;
    bytes += written;
    size -= (size_t)written;
  }
  return 1;
}

static void response(server_socket client, int code, const char *reason,
                     const char *mime, const unsigned char *body, size_t size,
                     int head) {
  char header[2048];
  int length = snprintf(header, sizeof(header),
    "HTTP/1.1 %d %s\r\n"
    "Content-Type: %s\r\nContent-Length: %lu\r\n"
    "Connection: close\r\nCache-Control: no-store\r\n"
    "X-Content-Type-Options: nosniff\r\n"
    "Cross-Origin-Resource-Policy: same-origin\r\n"
    "Referrer-Policy: no-referrer\r\n"
    "Content-Security-Policy: default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; "
    "worker-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'\r\n\r\n",
    code, reason, mime, (unsigned long)size);
  if (length < 0 || (size_t)length >= sizeof(header)) return;
  if (send_all(client, header, (size_t)length) && !head && size) send_all(client, body, size);
}

static int matches_header(const char *request, const char *header, const char *expected) {
  const char *line = strstr(request, "\r\n");
  const size_t name_length = strlen(header);
  while (line && line[2] && !(line[2] == '\r' && line[3] == '\n')) {
    line += 2;
    const char *end = strstr(line, "\r\n");
    if (!end) break;
    if ((size_t)(end - line) > name_length && line[name_length] == ':') {
      size_t i = 0;
      for (; i < name_length; ++i) {
        if (tolower((unsigned char)line[i]) != tolower((unsigned char)header[i])) break;
      }
      if (i == name_length) {
        const char *value = line + name_length + 1;
        while (value < end && (*value == ' ' || *value == '\t')) ++value;
        while (end > value && (end[-1] == ' ' || end[-1] == '\t')) --end;
        return (size_t)(end - value) == strlen(expected) &&
               memcmp(value, expected, (size_t)(end - value)) == 0;
      }
    }
    line = end;
  }
  return 0;
}

static void handle_client(server_socket client, unsigned short port) {
  char request[MAX_REQUEST + 1];
  size_t used = 0;
  while (used < MAX_REQUEST) {
    int n = recv(client, request + used, (int)(MAX_REQUEST - used), 0);
    if (n <= 0) return;
    used += (size_t)n;
    request[used] = '\0';
    if (strstr(request, "\r\n\r\n")) break;
  }
  static const unsigned char bad[] = "Solicitud rechazada.\n";
  if (used == MAX_REQUEST || !strstr(request, "\r\n\r\n")) {
    response(client, 431, "Headers Too Large", "text/plain; charset=utf-8", bad, sizeof(bad) - 1, 0);
    return;
  }
  char method[8], url[1024], version[16], host[64];
  if (sscanf(request, "%7s %1023s %15s", method, url, version) != 3 ||
      (strcmp(version, "HTTP/1.1") && strcmp(version, "HTTP/1.0"))) {
    response(client, 400, "Bad Request", "text/plain; charset=utf-8", bad, sizeof(bad) - 1, 0);
    return;
  }
  snprintf(host, sizeof(host), "127.0.0.1:%u", (unsigned)port);
  if (!matches_header(request, "Host", host)) {
    response(client, 403, "Forbidden", "text/plain; charset=utf-8", bad, sizeof(bad) - 1, 0);
    return;
  }
  const int head = strcmp(method, "HEAD") == 0;
  if (!head && strcmp(method, "GET")) {
    response(client, 405, "Method Not Allowed", "text/plain; charset=utf-8", bad, sizeof(bad) - 1, 0);
    return;
  }
  char *query = strchr(url, '?');
  if (query) *query = '\0';
  const char *path = strcmp(url, "/") == 0 ? "/index.html" : url;
  for (size_t i = 0; i < embedded_assets_count; ++i) {
    if (strcmp(path, embedded_assets[i].path) == 0) {
      response(client, 200, "OK", embedded_assets[i].mime,
               embedded_assets[i].bytes, embedded_assets[i].size, head);
      return;
    }
  }
  static const unsigned char missing[] = "Recurso no incluido.\n";
  response(client, 404, "Not Found", "text/plain; charset=utf-8", missing, sizeof(missing) - 1, head);
}

static unsigned short open_listener(unsigned short requested_port) {
  listener = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if (listener == INVALID_SOCKET) return 0;
  int exclusive = 1;
#ifdef _WIN32
  /* A second instance must NOT redirect the browser to a foreign process. */
  if (setsockopt(listener, SOL_SOCKET, SO_EXCLUSIVEADDRUSE,
                 (const char *)&exclusive, sizeof(exclusive)) == SOCKET_ERROR) return 0;
#else
  setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, &exclusive, sizeof(exclusive));
#endif
  struct sockaddr_in addr;
  memset(&addr, 0, sizeof(addr));
  addr.sin_family = AF_INET;
  addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  addr.sin_port = htons(requested_port);
  if (bind(listener, (struct sockaddr *)&addr, sizeof(addr)) == SOCKET_ERROR ||
      listen(listener, 16) == SOCKET_ERROR) return 0;
  socklen_t addr_length = (socklen_t)sizeof(addr);
  if (getsockname(listener, (struct sockaddr *)&addr, &addr_length) == SOCKET_ERROR) return 0;
  return ntohs(addr.sin_port);
}

#ifdef _WIN32
static DWORD WINAPI server_loop(LPVOID unused) {
  (void)unused;
  while (InterlockedCompareExchange(&running, 1, 1)) {
    server_socket client = accept(listener, NULL, NULL);
    if (client == INVALID_SOCKET) break;
    handle_client(client, APP_PORT);
    CLOSE_SOCKET(client);
  }
  return 0;
}

static void open_browser(HWND window) {
  HINSTANCE result = ShellExecuteW(window, L"open", browser_url, NULL, NULL, SW_SHOWNORMAL);
  if ((INT_PTR)result <= 32) MessageBoxW(window, L"No se pudo abrir el navegador. Usa el boton Abrir para reintentar.",
                                        L"ARQ GEN - navegador local", MB_OK | MB_ICONERROR);
}

static LRESULT CALLBACK window_proc(HWND window, UINT message, WPARAM wp, LPARAM lp) {
  switch (message) {
    case WM_CREATE:
      CreateWindowW(L"STATIC", L"ARQ GEN - Prototipo web local (NO Tauri)",
                    WS_CHILD | WS_VISIBLE, 18, 16, 400, 24, window, NULL, NULL, NULL);
      CreateWindowW(L"STATIC", L"Navegador externo en 127.0.0.1. Mantenga esta ventana abierta.",
                    WS_CHILD | WS_VISIBLE, 18, 45, 440, 24, window, NULL, NULL, NULL);
      CreateWindowW(L"STATIC", L"NO APTO PARA OBRA - sin QA Windows real.",
                    WS_CHILD | WS_VISIBLE, 18, 74, 400, 24, window, NULL, NULL, NULL);
      CreateWindowW(L"BUTTON", L"Abrir interfaz", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                    18, 112, 130, 34, window, (HMENU)(INT_PTR)101, NULL, NULL);
      CreateWindowW(L"BUTTON", L"Cerrar servidor", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                    165, 112, 130, 34, window, (HMENU)(INT_PTR)102, NULL, NULL);
      return 0;
    case WM_COMMAND:
      if (LOWORD(wp) == 101) open_browser(window);
      if (LOWORD(wp) == 102) DestroyWindow(window);
      return 0;
    case WM_CLOSE:
      DestroyWindow(window);
      return 0;
    case WM_DESTROY:
      InterlockedExchange(&running, 0);
      if (listener != INVALID_SOCKET) CLOSE_SOCKET(listener);
      PostQuitMessage(0);
      return 0;
    default: return DefWindowProcW(window, message, wp, lp);
  }
}

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command_line, int show) {
  (void)previous; (void)command_line; (void)show;
  WSADATA wsa;
  if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
    MessageBoxW(NULL, L"WinSock no disponible.", L"ARQ GEN - Error", MB_OK | MB_ICONERROR);
    return 1;
  }
  if (open_listener(APP_PORT) != APP_PORT) {
    MessageBoxW(NULL, L"No se puede reservar 127.0.0.1:48765. Cierre otra instancia o libere ese puerto.",
                L"ARQ GEN - Error", MB_OK | MB_ICONERROR);
    if (listener != INVALID_SOCKET) CLOSE_SOCKET(listener);
    WSACleanup();
    return 1;
  }
  server_thread_handle = CreateThread(NULL, 0, server_loop, NULL, 0, NULL);
  if (!server_thread_handle) {
    CLOSE_SOCKET(listener);
    WSACleanup();
    return 1;
  }
  swprintf(browser_url, sizeof(browser_url) / sizeof(browser_url[0]), L"http://127.0.0.1:%u/", APP_PORT);
  WNDCLASSW window_class;
  memset(&window_class, 0, sizeof(window_class));
  window_class.lpfnWndProc = window_proc;
  window_class.hInstance = instance;
  window_class.lpszClassName = L"ARQ_GEN_LOCAL_BROWSER_0_21";
  window_class.hCursor = LoadCursorW(NULL, MAKEINTRESOURCEW(32512));
  window_class.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
  if (!RegisterClassW(&window_class)) {
    CLOSE_SOCKET(listener); WaitForSingleObject(server_thread_handle, 2000);
    CloseHandle(server_thread_handle); WSACleanup(); return 1;
  }
  HWND window = CreateWindowW(window_class.lpszClassName, L"ARQ GEN - navegador local (prototipo)",
    WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
    CW_USEDEFAULT, CW_USEDEFAULT, 490, 220, NULL, NULL, instance, NULL);
  if (!window) {
    CLOSE_SOCKET(listener); WaitForSingleObject(server_thread_handle, 2000);
    CloseHandle(server_thread_handle); WSACleanup(); return 1;
  }
  ShowWindow(window, SW_SHOW);
  UpdateWindow(window);
  open_browser(window);
  MSG msg = {0};
  while (GetMessageW(&msg, NULL, 0, 0) > 0) {
    TranslateMessage(&msg);
    DispatchMessageW(&msg);
  }
  WaitForSingleObject(server_thread_handle, 2000);
  CloseHandle(server_thread_handle);
  WSACleanup();
  return (int)msg.wParam;
}
#else
static void close_from_signal(int signo) {
  (void)signo;
  running = 0;
  if (listener != INVALID_SOCKET) CLOSE_SOCKET(listener);
}
int main(void) {
  signal(SIGPIPE, SIG_IGN);
  signal(SIGTERM, close_from_signal);
  const char *env = getenv("ARQGEN_TEST_PORT");
  unsigned short port = APP_PORT;
  if (env) {
    char *end = NULL;
    unsigned long value = strtoul(env, &end, 10);
    if (*end || value > 65535) return 1;
    port = (unsigned short)value;
  }
  port = open_listener(port);
  if (!port) { fputs("No se pudo reservar localhost.\n", stderr); return 1; }
  printf("ARQGEN_LOCAL_URL=http://127.0.0.1:%u/\n", (unsigned)port);
  fflush(stdout);
  while (running) {
    server_socket client = accept(listener, NULL, NULL);
    if (client == INVALID_SOCKET) break;
    handle_client(client, port);
    CLOSE_SOCKET(client);
  }
  if (listener != INVALID_SOCKET) CLOSE_SOCKET(listener);
  return 0;
}
#endif
