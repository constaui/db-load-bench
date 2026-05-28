import java.io.*;
import java.sql.*;
import java.util.*;

public class InserterMySQL implements Inserter {

    private final Connection conn;

    public InserterMySQL(ConnParams p) throws SQLException {
        String url = String.format(
            "jdbc:mysql://%s:%d/%s?allowLoadLocalInfile=true&useSSL=false&serverTimezone=UTC",
            p.host, p.port, p.database
        );
        Properties props = new Properties();
        props.setProperty("user",     p.user);
        props.setProperty("password", p.password);
        props.setProperty("allowLoadLocalInfile", "true");

        conn = DriverManager.getConnection(url, props);

        try (Statement st = conn.createStatement()) {
            st.execute("SET GLOBAL local_infile = 1");
        }
    }

    @Override
    public void close() {
        try { if (conn != null) conn.close(); }
        catch (SQLException ignored) {}
    }

    private String quote(String name) {
        String clean = CSVReader.cleanIdentifier(name)
                                .replace("`", "``");
        return "`" + clean + "`";
    }

    @Override
    public int defaultInsert(String csvFile, String tableName) throws Exception {
        int total = 0;
        conn.setAutoCommit(false);
        try (CSVStream csv = new CSVStream(csvFile)) {
            String cols = buildCols(csv.headers);
            String phs  = buildPlaceholders(csv.headers.size(), false);
            String sql  = String.format("INSERT INTO %s (%s) VALUES (%s)",
                                        quote(tableName), cols, phs);

            try (PreparedStatement ps = conn.prepareStatement(sql)) {
                while (csv.hasNext()) {
                    String[] row = csv.next();
                    for (int i = 0; i < row.length; i++) {
                        ps.setString(i + 1, row[i]);
                    }
                    ps.executeUpdate();
                    total++;
                }
                conn.commit();
            }
        } catch (Exception e) {
            conn.rollback();
            throw e;
        } finally {
            conn.setAutoCommit(true);
        }
        return total;
    }

    @Override
    public int bulkInsert(String csvFile, String tableName, int batchSize) throws Exception {
        int total = 0;
        conn.setAutoCommit(false);
        try (CSVStream csv = new CSVStream(csvFile)) {
            String cols = buildCols(csv.headers);
            String phs  = buildPlaceholders(csv.headers.size(), false);
            String sql  = String.format("INSERT INTO %s (%s) VALUES (%s)",
                                        quote(tableName), cols, phs);

            try (PreparedStatement ps = conn.prepareStatement(sql)) {
                int count = 0;
                while (csv.hasNext()) {
                    String[] row = csv.next();
                    for (int i = 0; i < row.length; i++) {
                        ps.setString(i + 1, row[i]);
                    }
                    ps.addBatch();
                    count++;

                    if (count >= batchSize) {
                        ps.executeBatch();
                        total += count;
                        count = 0;
                    }
                }
                if (count > 0) {
                    ps.executeBatch();
                    total += count;
                }
                conn.commit();
            }
        } catch (Exception e) {
            conn.rollback();
            throw e;
        } finally {
            conn.setAutoCommit(true);
        }
        return total;
    }

    @Override
    public int fileInsert(String csvFile, String tableName) throws Exception {
        // НЕ парсим файл в Java — для LOAD DATA LOCAL INFILE сервер сам
        // читает CSV. CSVReader на 10⁷ строк давал OutOfMemoryError.
        File   f       = new File(csvFile);
        String absPath = f.getAbsolutePath().replace("\\", "/");

        String sql = String.format("""
            LOAD DATA LOCAL INFILE '%s'
            INTO TABLE %s
            FIELDS TERMINATED BY ','
            OPTIONALLY ENCLOSED BY '"'
            LINES TERMINATED BY '\\n'
            IGNORE 1 ROWS
            """, absPath, quote(tableName));

        int affected;
        conn.setAutoCommit(false);
        try (Statement st = conn.createStatement()) {
            // executeUpdate() для LOAD DATA INFILE возвращает количество
            // вставленных строк (из OK-пакета MySQL).
            affected = st.executeUpdate(sql);
            conn.commit();
        } catch (Exception e) {
            conn.rollback();
            throw e;
        } finally {
            conn.setAutoCommit(true);
        }

        return affected;
    }

    private String buildCols(List<String> headers) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < headers.size(); i++) {
            if (i > 0) sb.append(", ");
            sb.append(quote(headers.get(i)));
        }
        return sb.toString();
    }

    private String buildPlaceholders(int count, boolean numbered) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < count; i++) {
            if (i > 0) sb.append(", ");
            sb.append("?");
        }
        return sb.toString();
    }
}