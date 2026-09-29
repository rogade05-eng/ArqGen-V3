//! A small, strict JSON bridge for the dependency-free MVP-0 core.
//! Not a general replacement for serde: input size/depth are bounded and duplicate keys fail.
use std::collections::BTreeMap;

const MAX_BYTES: usize = 256 * 1024;
const MAX_DEPTH: usize = 40;

#[derive(Clone, Debug, PartialEq)]
pub enum Value {
    Null,
    Bool(bool),
    Number(f64),
    String(String),
    Array(Vec<Value>),
    Object(BTreeMap<String, Value>),
}

impl Value {
    pub fn get(&self, key: &str) -> Option<&Value> {
        match self {
            Value::Object(map) => map.get(key),
            _ => None,
        }
    }

    pub fn as_number(&self) -> Option<f64> {
        match self {
            Value::Number(value) => Some(*value),
            _ => None,
        }
    }

    pub fn as_str(&self) -> Option<&str> {
        match self {
            Value::String(value) => Some(value),
            _ => None,
        }
    }

    pub fn as_array(&self) -> Option<&[Value]> {
        match self {
            Value::Array(values) => Some(values),
            _ => None,
        }
    }

    pub fn insert(&mut self, key: impl Into<String>, value: Value) -> Result<(), String> {
        match self {
            Value::Object(map) => {
                map.insert(key.into(), value);
                Ok(())
            }
            _ => Err("se esperaba un objeto JSON".into()),
        }
    }

    pub fn stringify(&self) -> String {
        let mut result = String::new();
        self.write_to(&mut result);
        result
    }

    fn write_to(&self, out: &mut String) {
        match self {
            Value::Null => out.push_str("null"),
            Value::Bool(value) => out.push_str(if *value { "true" } else { "false" }),
            Value::Number(value) => {
                if value.is_finite() {
                    out.push_str(&value.to_string());
                } else {
                    // Non-finite numbers must never appear in JSON; fail closed.
                    out.push_str("null");
                }
            }
            Value::String(value) => write_string(out, value),
            Value::Array(items) => {
                out.push('[');
                for (index, item) in items.iter().enumerate() {
                    if index > 0 {
                        out.push(',');
                    }
                    item.write_to(out);
                }
                out.push(']');
            }
            Value::Object(map) => {
                out.push('{');
                for (index, (key, item)) in map.iter().enumerate() {
                    if index > 0 {
                        out.push(',');
                    }
                    write_string(out, key);
                    out.push(':');
                    item.write_to(out);
                }
                out.push('}');
            }
        }
    }
}

pub fn object(fields: Vec<(&str, Value)>) -> Value {
    Value::Object(
        fields
            .into_iter()
            .map(|(key, value)| (key.to_string(), value))
            .collect(),
    )
}

pub fn text(value: impl Into<String>) -> Value {
    Value::String(value.into())
}
pub fn number(value: f64) -> Value {
    Value::Number(value)
}
pub fn list(values: impl IntoIterator<Item = Value>) -> Value {
    Value::Array(values.into_iter().collect())
}

fn write_string(out: &mut String, value: &str) {
    out.push('"');
    for ch in value.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c < ' ' => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
}

pub fn parse(source: &str) -> Result<Value, String> {
    parse_with_limit(source, MAX_BYTES)
}

/// Parse our own bounded WASM/CLI response, never an untrusted request.
/// A batch can legitimately exceed the 256 KiB input limit.
pub fn parse_response(source: &str) -> Result<Value, String> {
    parse_with_limit(source, 2_000_000)
}

fn parse_with_limit(source: &str, max_bytes: usize) -> Result<Value, String> {
    if source.len() > max_bytes {
        return Err(if max_bytes == MAX_BYTES {
            "JSON demasiado grande (máximo 256 KiB)".into()
        } else {
            format!("Respuesta JSON demasiado grande (máximo {max_bytes} bytes)")
        });
    }
    let mut parser = Parser {
        bytes: source.as_bytes(),
        pos: 0,
    };
    let value = parser.value(0)?;
    parser.whitespace();
    if parser.pos != parser.bytes.len() {
        return parser.fail("contenido después del valor JSON");
    }
    Ok(value)
}

struct Parser<'a> {
    bytes: &'a [u8],
    pos: usize,
}

impl Parser<'_> {
    fn fail<T>(&self, message: &str) -> Result<T, String> {
        Err(format!("JSON, byte {}: {}", self.pos, message))
    }

    fn whitespace(&mut self) {
        while self.pos < self.bytes.len()
            && matches!(self.bytes[self.pos], b' ' | b'\r' | b'\n' | b'\t')
        {
            self.pos += 1;
        }
    }

    fn take(&mut self, expected: u8) -> Result<(), String> {
        if self.bytes.get(self.pos) == Some(&expected) {
            self.pos += 1;
            Ok(())
        } else {
            self.fail(&format!("se esperaba '{}'", expected as char))
        }
    }

    fn value(&mut self, depth: usize) -> Result<Value, String> {
        if depth > MAX_DEPTH {
            return self.fail("JSON demasiado anidado");
        }
        self.whitespace();
        match self.bytes.get(self.pos) {
            Some(b'{') => self.object(depth + 1),
            Some(b'[') => self.array(depth + 1),
            Some(b'"') => Ok(Value::String(self.string()?)),
            Some(b't') => {
                self.keyword(b"true")?;
                Ok(Value::Bool(true))
            }
            Some(b'f') => {
                self.keyword(b"false")?;
                Ok(Value::Bool(false))
            }
            Some(b'n') => {
                self.keyword(b"null")?;
                Ok(Value::Null)
            }
            Some(b'-' | b'0'..=b'9') => Ok(Value::Number(self.numeric()?)),
            _ => self.fail("valor JSON no reconocido"),
        }
    }

    fn keyword(&mut self, keyword: &[u8]) -> Result<(), String> {
        if self.bytes.get(self.pos..self.pos + keyword.len()) == Some(keyword) {
            self.pos += keyword.len();
            Ok(())
        } else {
            self.fail("palabra clave inválida")
        }
    }

    fn object(&mut self, depth: usize) -> Result<Value, String> {
        self.take(b'{')?;
        self.whitespace();
        let mut fields = BTreeMap::new();
        if self.bytes.get(self.pos) == Some(&b'}') {
            self.pos += 1;
            return Ok(Value::Object(fields));
        }
        loop {
            self.whitespace();
            if self.bytes.get(self.pos) != Some(&b'"') {
                return self.fail("la clave debe ser texto");
            }
            let key = self.string()?;
            self.whitespace();
            self.take(b':')?;
            let value = self.value(depth)?;
            if fields.insert(key.clone(), value).is_some() {
                return self.fail(&format!("clave duplicada: {key}"));
            }
            self.whitespace();
            match self.bytes.get(self.pos) {
                Some(b',') => self.pos += 1,
                Some(b'}') => {
                    self.pos += 1;
                    return Ok(Value::Object(fields));
                }
                _ => return self.fail("se esperaba ',' o '}'"),
            }
        }
    }

    fn array(&mut self, depth: usize) -> Result<Value, String> {
        self.take(b'[')?;
        self.whitespace();
        let mut items = Vec::new();
        if self.bytes.get(self.pos) == Some(&b']') {
            self.pos += 1;
            return Ok(Value::Array(items));
        }
        loop {
            items.push(self.value(depth)?);
            self.whitespace();
            match self.bytes.get(self.pos) {
                Some(b',') => self.pos += 1,
                Some(b']') => {
                    self.pos += 1;
                    return Ok(Value::Array(items));
                }
                _ => return self.fail("se esperaba ',' o ']'"),
            }
        }
    }

    fn string(&mut self) -> Result<String, String> {
        self.take(b'"')?;
        let mut result = Vec::new();
        while let Some(&byte) = self.bytes.get(self.pos) {
            self.pos += 1;
            match byte {
                b'"' => return String::from_utf8(result).map_err(|_| "UTF-8 inválido".into()),
                b'\\' => match self.bytes.get(self.pos).copied() {
                    Some(b'"' | b'\\' | b'/') => {
                        result.push(self.bytes[self.pos]);
                        self.pos += 1;
                    }
                    Some(b'b') => {
                        result.push(8);
                        self.pos += 1;
                    }
                    Some(b'f') => {
                        result.push(12);
                        self.pos += 1;
                    }
                    Some(b'n') => {
                        result.push(b'\n');
                        self.pos += 1;
                    }
                    Some(b'r') => {
                        result.push(b'\r');
                        self.pos += 1;
                    }
                    Some(b't') => {
                        result.push(b'\t');
                        self.pos += 1;
                    }
                    Some(b'u') => {
                        self.pos += 1;
                        let first = self.hex4()?;
                        let scalar = if (0xd800..=0xdbff).contains(&first) {
                            self.take(b'\\')?;
                            self.take(b'u')?;
                            let second = self.hex4()?;
                            if !(0xdc00..=0xdfff).contains(&second) {
                                return self.fail("pareja surrogate inválida");
                            }
                            0x10000 + ((first as u32 - 0xd800) << 10) + (second as u32 - 0xdc00)
                        } else {
                            first as u32
                        };
                        let ch = char::from_u32(scalar)
                            .ok_or_else(|| format!("JSON, byte {}: Unicode inválido", self.pos))?;
                        let mut encoded = [0; 4];
                        result.extend_from_slice(ch.encode_utf8(&mut encoded).as_bytes());
                    }
                    _ => return self.fail("escape JSON inválido"),
                },
                0..=31 => return self.fail("carácter de control sin escape"),
                _ => result.push(byte),
            }
        }
        self.fail("cadena sin cierre")
    }

    fn hex4(&mut self) -> Result<u16, String> {
        let mut value = 0_u16;
        for _ in 0..4 {
            let digit = match self.bytes.get(self.pos) {
                Some(b'0'..=b'9') => self.bytes[self.pos] - b'0',
                Some(b'a'..=b'f') => self.bytes[self.pos] - b'a' + 10,
                Some(b'A'..=b'F') => self.bytes[self.pos] - b'A' + 10,
                _ => return self.fail("escape Unicode incompleto"),
            };
            value = value * 16 + digit as u16;
            self.pos += 1;
        }
        Ok(value)
    }

    fn numeric(&mut self) -> Result<f64, String> {
        let start = self.pos;
        if self.bytes.get(self.pos) == Some(&b'-') {
            self.pos += 1;
        }
        match self.bytes.get(self.pos) {
            Some(b'0') => self.pos += 1,
            Some(b'1'..=b'9') => {
                self.pos += 1;
                while matches!(self.bytes.get(self.pos), Some(b'0'..=b'9')) {
                    self.pos += 1;
                }
            }
            _ => return self.fail("número inválido"),
        }
        if self.bytes.get(self.pos) == Some(&b'.') {
            self.pos += 1;
            let fraction_start = self.pos;
            while matches!(self.bytes.get(self.pos), Some(b'0'..=b'9')) {
                self.pos += 1;
            }
            if fraction_start == self.pos {
                return self.fail("fracción vacía");
            }
        }
        if matches!(self.bytes.get(self.pos), Some(b'e' | b'E')) {
            self.pos += 1;
            if matches!(self.bytes.get(self.pos), Some(b'+' | b'-')) {
                self.pos += 1;
            }
            let exponent_start = self.pos;
            while matches!(self.bytes.get(self.pos), Some(b'0'..=b'9')) {
                self.pos += 1;
            }
            if exponent_start == self.pos {
                return self.fail("exponente vacío");
            }
        }
        let text = std::str::from_utf8(&self.bytes[start..self.pos])
            .map_err(|_| "número mal codificado".to_string())?;
        let value = text
            .parse::<f64>()
            .map_err(|_| "número inválido".to_string())?;
        if !value.is_finite() {
            return self.fail("número no finito");
        }
        Ok(value)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strict_json_and_unicode() {
        let input = r#"{"nombre":"baño \ud83c\udfe0","v":[true,null,-0.25e2]}"#;
        let parsed = parse(input).unwrap();
        assert_eq!(parsed.get("nombre").unwrap().as_str(), Some("baño 🏠"));
        assert_eq!(parse(&parsed.stringify()).unwrap(), parsed);
    }

    #[test]
    fn rejects_duplicate_keys_and_bad_numbers() {
        for input in [
            r#"{"a":1,"a":2}"#,
            r#"{"a":01}"#,
            "1e500",
            r#""\ud800""#,
            "[1,]",
        ] {
            assert!(parse(input).is_err(), "debería fallar: {input}");
        }
    }

    #[test]
    fn escaping_is_safe() {
        let source = "<test> \"&\n\u{0001}";
        let encoded = text(source).stringify();
        assert_eq!(parse(&encoded).unwrap().as_str(), Some(source));
    }
}
