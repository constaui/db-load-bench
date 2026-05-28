public interface Inserter extends AutoCloseable {
    int defaultInsert(String csvFile, String tableName) throws Exception;
    int bulkInsert(String csvFile, String tableName, int batchSize) throws Exception;
    int fileInsert(String csvFile, String tableName) throws Exception;

    /**
     * Возвращает фактическое число строк в таблице через {@code SELECT COUNT(*)}.
     * Используется в Main для независимой проверки результата вставки — число
     * берётся из самой БД, а не из CSV, не из счётчика драйвера и не из
     * счётчика итераций.
     */
    int countRows(String tableName) throws Exception;

    void close();
}