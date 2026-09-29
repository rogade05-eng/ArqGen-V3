// Minimal W3C WebDriver transport, without a second browser runner or Tauri IPC.
// It talks only to the local tauri-driver -> Microsoft EdgeDriver -> WebView2 chain.
const elementKey = 'element-6066-11e4-a52e-4f735466cecf';

export class NativeWebDriver {
  constructor(origin = 'http://127.0.0.1:4444') {
    const url = new URL(origin);
    if (!['127.0.0.1', 'localhost'].includes(url.hostname) || url.protocol !== 'http:') {
      throw new Error('El WebDriver nativo debe escucharse únicamente en localhost por HTTP.');
    }
    this.origin = url.origin;
    this.sessionId = null;
  }

  async command(method, path, payload, timeout = 30_000) {
    const response = await fetch(`${this.origin}${path}`, {
      method,
      headers: payload === undefined ? undefined : { 'content-type': 'application/json' },
      body: payload === undefined ? undefined : JSON.stringify(payload),
      signal: AbortSignal.timeout(timeout),
    });
    const text = await response.text();
    let body;
    try { body = text ? JSON.parse(text) : { value: null }; }
    catch { throw new Error(`Respuesta WebDriver no JSON (${response.status}): ${text.slice(0, 200)}`); }
    if (!body || typeof body !== 'object' || !Object.hasOwn(body, 'value')) {
      throw new Error(`Respuesta WebDriver no W3C (${response.status}): ${text.slice(0, 200)}`);
    }
    if (!response.ok || body.value?.error) {
      throw new Error(`WebDriver ${method} ${path}: ${body.value?.message || body.message || response.status}`);
    }
    return body.value;
  }

  route(suffix) {
    if (!this.sessionId) throw new Error('No hay sesión WebView2 nativa; Chromium web no sustituye este QA.');
    return `/session/${encodeURIComponent(this.sessionId)}${suffix}`;
  }

  async open(application) {
    if (this.sessionId) throw new Error('Solo se permite una sesión nativa activa.');
    const value = await this.command('POST', '/session', {
      capabilities: { alwaysMatch: {
        browserName: 'wry',
        'tauri:options': { application },
      } },
    }, 90_000);
    if (typeof value?.sessionId !== 'string' || !value.sessionId) {
      throw new Error('tauri-driver no creó una sesión W3C/WebView2 válida.');
    }
    this.sessionId = value.sessionId;
    return value.capabilities;
  }

  execute(script, args = []) {
    return this.command('POST', this.route('/execute/sync'), { script, args });
  }

  async element(selector) {
    const value = await this.command('POST', this.route('/element'),
      { using: 'css selector', value: selector });
    const id = value?.[elementKey] || value?.ELEMENT;
    if (typeof id !== 'string' || !id) throw new Error(`Elemento no encontrado: ${selector}`);
    return id;
  }

  async click(selector) {
    const id = await this.element(selector);
    await this.command('POST', this.route(`/element/${encodeURIComponent(id)}/click`), {});
  }

  async sendFile(selector, absolutePath) {
    const id = await this.element(selector);
    await this.command('POST', this.route(`/element/${encodeURIComponent(id)}/value`), {
      text: absolutePath,
      value: Array.from(absolutePath),
    });
  }

  refresh() { return this.command('POST', this.route('/refresh'), {}); }
  screenshot() { return this.command('GET', this.route('/screenshot')); }
  async close() {
    if (!this.sessionId) return;
    const path = this.route('');
    this.sessionId = null;
    await this.command('DELETE', path);
  }
}
