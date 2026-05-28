use crate::csv::{CsvStream, clean_identifier};
use crate::inserter::{ConnParams, Inserter};
use anyhow::{Result, anyhow};
use mysql::prelude::*;
use mysql::*;
use std::io::Read;

/// Определяет line-ending CSV-файла без декодирования.
/// Возвращает строку-аргумент для LOAD DATA LINES TERMINATED BY:
/// `\r\n` (Windows-стиль) или `\n`. Без этого LOAD DATA на Windows-файле
/// может потерять разбиение строк и оставить в таблице 1 битую запись.
fn detect_lines_terminator(path: &str) -> std::io::Result<&'static str> {
    let mut file = std::fs::File::open(path)?;
    let mut buf = [0u8; 8192];
    let n = file.read(&mut buf)?;
    if buf[..n].windows(2).any(|w| w == b"\r\n") {
        Ok(r"\r\n")
    } else {
        Ok(r"\n")
    }
}

pub struct MySQLInserter {
    conn: Conn,
}

impl MySQLInserter {
    pub fn new(p: &ConnParams) -> Result<Self> {
        let url = format!(
            "mysql://{}:{}@{}:{}/{}",
            p.user, p.password, p.host, p.port, p.database
        );

        let builder = OptsBuilder::from_opts(Opts::from_url(&url)?)
            .local_infile_handler(Some(LocalInfileHandler::new(
                |file_name: &[u8], infile: &mut mysql::LocalInfile<'_>| {
                    // Стримим файл прямо в сокет, без загрузки в Vec<u8>.
                    let path = String::from_utf8_lossy(file_name).to_string();
                    let mut file = std::fs::File::open(&path)?;
                    std::io::copy(&mut file, infile)?;
                    Ok(())
                },
            )));

        let conn = Conn::new(builder)?;
        Ok(Self { conn })
    }

    fn quote(name: &str) -> String {
        let clean = clean_identifier(name);
        format!("`{}`", clean.replace('`', "``"))
    }

    fn build_cols(headers: &[String]) -> String {
        headers.iter()
            .map(|h| Self::quote(h))
            .collect::<Vec<_>>()
            .join(", ")
    }
}

impl Inserter for MySQLInserter {

    fn count_rows(&mut self, table: &str) -> Result<usize> {
        let sql = format!("SELECT COUNT(*) FROM {}", Self::quote(table));
        let row: Option<i64> = self.conn.query_first(&sql)?;
        Ok(row.unwrap_or(0) as usize)
    }

    fn default_insert(&mut self, csv_file: &str, table: &str) -> Result<usize> {
        let mut stream = CsvStream::open(csv_file)?;
        let cols  = Self::build_cols(&stream.headers);
        let phs   = vec!["?"; stream.headers.len()].join(", ");
        let sql   = format!("INSERT INTO {} ({}) VALUES ({})",
                            Self::quote(table), cols, phs);

        let mut tx = self.conn.start_transaction(TxOpts::default())?;
        let mut count = 0;
        while let Some(row) = stream.next() {
            let row = row?;
            let params: Vec<Value> = row.iter()
                .map(|v| Value::Bytes(v.as_bytes().to_vec()))
                .collect();
            tx.exec_drop(&sql, params)?;
            count += 1;
        }
        tx.commit()?;
        Ok(count)
    }

    fn bulk_insert(&mut self, csv_file: &str, table: &str,
                   batch_size: usize) -> Result<usize> {
        let mut stream = CsvStream::open(csv_file)?;
        let cols   = Self::build_cols(&stream.headers);
        let qtable = Self::quote(table);
        let ncols  = stream.headers.len();
        let mut total = 0;

        // Шаблон одной группы плейсхолдеров `(?, ?, …)` строим один раз.
        let row_phs = format!("({})", vec!["?"; ncols].join(", "));

        let mut batch: Vec<Vec<String>> = Vec::with_capacity(batch_size);
        let mut eof = false;

        while !eof {
            match stream.next() {
                Some(Ok(row)) => batch.push(row),
                Some(Err(e))  => return Err(e),
                None          => eof = true,
            }

            // Шлём пачку, когда она накопилась до batch_size или CSV кончился.
            if (batch.len() >= batch_size || (eof && !batch.is_empty())) && !batch.is_empty() {
                let all_phs = vec![row_phs.as_str(); batch.len()].join(", ");
                let sql = format!("INSERT INTO {} ({}) VALUES {}",
                                  qtable, cols, all_phs);

                let params: Vec<Value> = batch.iter()
                    .flat_map(|row| row.iter()
                        .map(|v| Value::Bytes(v.as_bytes().to_vec())))
                    .collect();

                let mut tx = self.conn.start_transaction(TxOpts::default())?;
                tx.exec_drop(&sql, params)?;
                tx.commit()?;
                total += batch.len();
                batch.clear();
            }
        }

        Ok(total)
    }

    fn file_insert(&mut self, csv_file: &str, table: &str) -> Result<usize> {
        // Парсить файл не нужно — LOAD DATA INFILE даёт серверу прочитать его
        // самостоятельно. Возвращаемое значение метода больше не используется
        // в main: фактическое число строк main получает через count_rows()
        // уже после замера времени.
        let raw_path = std::path::PathBuf::from(csv_file);
        let abs_path = if raw_path.is_absolute() {
            raw_path
        } else {
            std::env::current_dir()?.join(raw_path)
        };

        // Backslash → forward slash: безопасно и для Windows API, и для MySQL.
        let sql_path = abs_path.to_string_lossy().replace('\\', "/");

        let line_term = detect_lines_terminator(csv_file)
            .map_err(|e| anyhow!("detect line endings: {}", e))?;

        let sql = format!(
            "LOAD DATA LOCAL INFILE '{}' \
            INTO TABLE {} \
            FIELDS TERMINATED BY ',' \
            OPTIONALLY ENCLOSED BY '\"' \
            LINES TERMINATED BY '{}' \
            IGNORE 1 ROWS",
            sql_path,
            Self::quote(table),
            line_term
        );

        self.conn
            .query_drop(sql)
            .map_err(|e| anyhow!("LOAD DATA error: {}", e))?;

        Ok(0)
    }
}
