use std::fs::File;
use std::io::{BufRead, BufReader, Lines};

/// Очищает идентификатор/значение от обрамляющих кавычек и пробелов.
pub fn clean_identifier(s: &str) -> String {
    let mut result = s.to_string();
    loop {
        let prev = result.clone();
        let stripped = result.trim();
        let stripped = stripped
            .trim_matches('"')
            .trim_matches('`')
            .trim_matches('\'')
            .trim();
        result = stripped.to_string();
        if result == prev {
            break;
        }
    }
    result
}

fn unwrap_outer(line: &str) -> String {
    let s = line.trim();
    if s.starts_with('"') && s.ends_with('"') && s.len() >= 2 {
        s[1..s.len() - 1].to_string()
    } else {
        s.to_string()
    }
}

fn replace_double_quotes(s: &str) -> String {
    s.replace("\"\"", "\"")
}

fn parse_csv_line(line: &str) -> Vec<String> {
    let mut fields    = Vec::new();
    let mut current   = String::new();
    let mut in_quotes = false;
    let chars: Vec<char> = line.chars().collect();
    let mut i = 0;

    while i <= chars.len() {
        let c = chars.get(i).copied();
        match c {
            Some('"') => {
                if in_quotes && chars.get(i + 1) == Some(&'"') {
                    current.push('"');
                    i += 1;
                } else {
                    in_quotes = !in_quotes;
                }
            }
            Some(',') if !in_quotes => {
                fields.push(current.clone());
                current.clear();
            }
            None => {
                fields.push(current.clone());
                current.clear();
            }
            Some(ch) => current.push(ch),
        }
        i += 1;
    }

    fields
}

fn parse_wrapped_line(line: &str) -> Vec<String> {
    let unwrapped  = unwrap_outer(line);
    let normalized = replace_double_quotes(&unwrapped);
    parse_csv_line(&normalized)
        .into_iter()
        .map(|f| clean_identifier(&f))
        .collect()
}

/// Потоковый CSV-итератор. Читает файл по одной строке через `BufReader::lines`
/// и возвращает каждую обработанную строку через `Iterator::next`. Не грузит
/// файл в память — годится для CSV в миллионы строк.
///
/// Использование:
/// ```ignore
/// let mut stream = CsvStream::open(path)?;
/// for row in stream.by_ref() {
///     let row = row?;
///     // ...
/// }
/// ```
pub struct CsvStream {
    pub headers: Vec<String>,
    lines: Lines<BufReader<File>>,
}

impl CsvStream {
    pub fn open(path: &str) -> anyhow::Result<Self> {
        let file = File::open(path)
            .map_err(|e| anyhow::anyhow!("open: {}", e))?;
        // 1 МБ буфер — достаточно даже для длинных строк CSV.
        let reader = BufReader::with_capacity(1 << 20, file);
        let mut lines = reader.lines();

        // Первая непустая строка — заголовок.
        let header_line = loop {
            match lines.next() {
                None => anyhow::bail!("csv is empty"),
                Some(Err(e)) => return Err(anyhow::anyhow!("read header: {}", e)),
                Some(Ok(s)) => {
                    if !s.trim().is_empty() {
                        break s;
                    }
                }
            }
        };

        let mut headers = parse_wrapped_line(&header_line);
        if let Some(first) = headers.first_mut() {
            *first = first.trim_start_matches('\u{FEFF}').to_string();
        }

        Ok(CsvStream { headers, lines })
    }
}

impl Iterator for CsvStream {
    type Item = anyhow::Result<Vec<String>>;

    fn next(&mut self) -> Option<Self::Item> {
        loop {
            match self.lines.next()? {
                Err(e) => return Some(Err(anyhow::anyhow!("read line: {}", e))),
                Ok(line) => {
                    if line.trim().is_empty() {
                        continue;
                    }
                    return Some(Ok(parse_wrapped_line(&line)));
                }
            }
        }
    }
}
