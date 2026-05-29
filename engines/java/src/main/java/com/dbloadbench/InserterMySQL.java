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

    @Override
    public int countRows(String tableName) throws Exception {
        String sql = "SELECT COUNT(*) FROM " + quote(tableName);
        try (Statement st = conn.createStatement();
             ResultSet rs = st.executeQuery(sql)) {
            return rs.next() ? rs.getInt(1) : 0;
        }
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
        // НЕ парсим файл в Java — сервер MySQL сам читает CSV через
        // LOAD DATA LOCAL INFILE. Возвращаемое значение метода больше не
        // используется в Main: фактическое число строк Main получает через
        // countRows() уже после замера времени.
        File   f        = new File(csvFile);
        String absPath  = f.getAbsolutePath().replace("\\", "/");
        String lineTerm = CSVReader.detectLinesTerminator(csvFile);

        String sql = String.format("""
            LOAD DATA LOCAL INFILE '%s'
            INTO TABLE %s
            FIELDS TERMINATED BY ','
            OPTIONALLY ENCLOSED BY '"'
            LINES TERMINATED BY '%s'
            IGNORE 1 ROWS
            """, absPath, quote(tableName), lineTerm);

        conn.setAutoCommit(false);
        try (Statement st = conn.createStatement()) {
            st.executeUpdate(sql);
            // Диагностика: вытаскиваем все warnings от LOAD DATA.
            // Если MySQL не разобрал файл (line endings, кавычки, число
            // колонок), именно warnings скажут что не так.
            try (ResultSet rs = st.executeQuery("SHOW WARNINGS")) {
                int n = 0;
                while (rs.next()) {
                    if (n == 0) {
                        System.err.println("[MySQL LOAD DATA warnings]");
                    }
                    if (n < 10) {
                        System.err.printf("  %s %s: %s%n",
                            rs.getString(1), rs.getString(2), rs.getString(3));
                    }
                    n++;
                }
                if (n > 10) {
                    System.err.printf("  ... ещё %d warnings%n", n - 10);
                }
            }
            conn.commit();
        } catch (Exception e) {
            conn.rollback();
            throw e;
        } finally {
            conn.setAutoCommit(true);
        }

        return 0;
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