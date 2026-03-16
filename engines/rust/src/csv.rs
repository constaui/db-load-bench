#[derive(Debug)]
pub struct CSVData {
    pub headers: Vec<String>,
    pub rows:    Vec<Vec<String>>,
}

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

pub fn csv_read(path: &str) -> anyhow::Result<CSVData> {
    let content = std::fs::read_to_string(path)
        .map_err(|e| anyhow::anyhow!("csv_read: {}", e))?;

    let mut lines: Vec<&str> = content
        .lines()
        .filter(|l| !l.trim().is_empty())
        .collect();

    if lines.is_empty() {
        anyhow::bail!("csv_read: file is empty");
    }

    let mut headers = parse_wrapped_line(lines[0]);

    if let Some(first) = headers.first_mut() {
        *first = first.trim_start_matches('\u{FEFF}').to_string();
    }

    lines.remove(0);
    let rows = lines.iter().map(|l| parse_wrapped_line(l)).collect();

    Ok(CSVData { headers, rows })
}