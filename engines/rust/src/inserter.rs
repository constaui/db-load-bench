use anyhow::Result;

pub struct ConnParams {
    pub host:     String,
    pub port:     u16,
    pub user:     String,
    pub password: String,
    pub database: String,
}

pub trait Inserter {
    fn default_insert(&mut self, csv_file: &str, table: &str) -> Result<usize>;
    fn bulk_insert(&mut self, csv_file: &str, table: &str, batch_size: usize) -> Result<usize>;
    fn file_insert(&mut self, csv_file: &str, table: &str) -> Result<usize>;

    /// Возвращает фактическое число строк в таблице через `SELECT COUNT(*)`.
    /// Используется в `main` для независимой проверки результата вставки —
    /// число берётся именно из БД, а не из CSV и не из счётчиков драйвера.
    fn count_rows(&mut self, table: &str) -> Result<usize>;
}