use crate::csv::{CsvStream, clean_identifier};
use crate::inserter::{ConnParams, Inserter};
use anyhow::{Result, anyhow};
use postgres::{Client, NoTls};
use std::fmt::Write;
use std::io::BufRead;

pub struct PgSQLInserter {
    client: Client,
}

impl PgSQLInserter {
    pub fn new(p: &ConnParams) -> Result<Self> {
        let dsn = format!(
            "host={} port={} user={} password={} dbname={} sslmode=disable",
            p.host, p.port, p.user, p.password, p.database
        );
        let client = Client::connect(&dsn, NoTls)?;
        Ok(Self { client })
    }

    fn quote(name: &str) -> String {
        let clean = clean_identifier(name);
        format!("\"{}\"", clean.replace('"', "\"\""))
    }

    fn build_cols(headers: &[String]) -> String {
        headers.iter()
            .map(|h| Self::quote(h))
            .collect::<Vec<_>>()
            .join(", ")
    }

    fn build_placeholders(count: usize) -> String {
        (1..=count)
            .map(|i| format!("${}", i))
            .collect::<Vec<_>>()
            .join(", ")
    }
}

impl Inserter for PgSQLInserter {

    fn default_insert(&mut self, csv_file: &str, table: &str) -> Result<usize> {
        let mut stream = CsvStream::open(csv_file)?;
        let ncols = stream.headers.len();
        let sql   = format!(
            "INSERT INTO {} ({}) VALUES ({})",
            Self::quote(table),
            Self::build_cols(&stream.headers),
            Self::build_placeholders(ncols),
        );

        let stmt = self.client.prepare(&sql)?;
        let mut tx = self.client.transaction()?;
        let mut count = 0;

        while let Some(row) = stream.next() {
            let row = row?;
            let params: Vec<&(dyn postgres::types::ToSql + Sync)> = row.iter()
                .map(|v| v as &(dyn postgres::types::ToSql + Sync))
                .collect();
            tx.execute(&stmt, &params)?;
            count += 1;
        }
        tx.commit()?;
        Ok(count)
    }

    fn bulk_insert(&mut self, csv_file: &str, table: &str,
                   batch_size: usize) -> Result<usize> {
        let mut stream = CsvStream::open(csv_file)?;
        let ncols  = stream.headers.len();
        let cols   = Self::build_cols(&stream.headers);
        let qtable = Self::quote(table);
        let mut total = 0;

        let mut batch: Vec<Vec<String>> = Vec::with_capacity(batch_size);
        let mut eof = false;

        while !eof {
            match stream.next() {
                Some(Ok(row)) => batch.push(row),
                Some(Err(e))  => return Err(e),
                None          => eof = true,
            }

            if (batch.len() >= batch_size || (eof && !batch.is_empty())) && !batch.is_empty() {
                // Собираем (..., $i, $i+1, ...), ($j, ...) — нумерация
                // плейсхолдеров глобальная для всего запроса.
                let mut sql = format!("INSERT INTO {} ({}) VALUES ", qtable, cols);
                let mut param_idx = 1;
                for (r, _) in batch.iter().enumerate() {
                    if r > 0 { sql.push_str(", "); }
                    sql.push('(');
                    for c in 0..ncols {
                        if c > 0 { sql.push_str(", "); }
                        write!(sql, "${}", param_idx).unwrap();
                        param_idx += 1;
                    }
                    sql.push(')');
                }

                let params: Vec<&(dyn postgres::types::ToSql + Sync)> = batch.iter()
                    .flat_map(|row| row.iter()
                        .map(|v| v as &(dyn postgres::types::ToSql + Sync)))
                    .collect();

                let mut tx = self.client.transaction()?;
                tx.execute(sql.as_str(), &params)?;
                tx.commit()?;
                total += batch.len();
                batch.clear();
            }
        }

        Ok(total)
    }

    fn file_insert(&mut self, csv_file: &str, table: &str) -> Result<usize> {
        // Считаем строки за один поток (без загрузки файла в память).
        let row_count = {
            let file = std::fs::File::open(csv_file)
                .map_err(|e| anyhow!("open: {}", e))?;
            let reader = std::io::BufReader::new(file);
            reader.lines().count().saturating_sub(1)
        };

        let copy_sql = format!(
            "COPY {} FROM STDIN WITH (FORMAT csv, HEADER true)",
            Self::quote(table)
        );

        let mut writer = self.client
            .copy_in(&copy_sql)
            .map_err(|e| anyhow!("COPY error: {}", e))?;

        let mut file = std::fs::File::open(csv_file)
            .map_err(|e| anyhow!("open file: {}", e))?;
        std::io::copy(&mut file, &mut writer)
            .map_err(|e| anyhow!("COPY write error: {}", e))?;

        writer.finish()
            .map_err(|e| anyhow!("COPY finish error: {}", e))?;

        Ok(row_count)
    }
}
