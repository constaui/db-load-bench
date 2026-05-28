import java.io.*;
import java.util.*;

/**
 * Потоковый CSV-ридер. В отличие от {@link CSVReader} (статические утилиты),
 * не загружает файл в память — читает построчно по запросу.
 *
 * Используется в default_insert и bulk_insert, чтобы не упирать heap JVM
 * на больших объёмах данных.
 *
 * Применение:
 *   try (CSVStream csv = new CSVStream(path)) {
 *       List<String> headers = csv.headers;
 *       while (csv.hasNext()) {
 *           String[] row = csv.next();
 *           ...
 *       }
 *   }
 */
public class CSVStream implements Iterator<String[]>, Closeable {

    public final List<String> headers;

    private final BufferedReader reader;
    private String[] nextRow;
    private boolean  nextLoaded;
    private boolean  exhausted;

    public CSVStream(String path) throws IOException {
        this.reader = new BufferedReader(
            new InputStreamReader(new FileInputStream(path), "UTF-8"),
            1 << 20  // 1 МБ буфер чтения
        );

        String headerLine = reader.readLine();
        if (headerLine == null) {
            reader.close();
            throw new IOException("CSV is empty");
        }
        if (headerLine.startsWith("﻿")) {
            headerLine = headerLine.substring(1);
        }

        String[] rawHeaders = CSVReader.parseCsvLine(headerLine.trim());
        List<String> hdrs = new ArrayList<>(rawHeaders.length);
        for (String h : rawHeaders) {
            hdrs.add(CSVReader.cleanIdentifier(h));
        }
        this.headers = hdrs;
    }

    @Override
    public boolean hasNext() {
        if (exhausted) return false;
        if (nextLoaded) return nextRow != null;

        try {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.trim().isEmpty()) continue;

                String[] row = CSVReader.parseCsvLine(line);
                for (int i = 0; i < row.length; i++) {
                    row[i] = CSVReader.cleanIdentifier(row[i]);
                }
                nextRow    = row;
                nextLoaded = true;
                return true;
            }
            nextRow    = null;
            nextLoaded = true;
            exhausted  = true;
            return false;
        } catch (IOException e) {
            throw new UncheckedIOException("read csv: " + e.getMessage(), e);
        }
    }

    @Override
    public String[] next() {
        if (!hasNext()) throw new NoSuchElementException();
        nextLoaded = false;
        return nextRow;
    }

    @Override
    public void close() throws IOException {
        reader.close();
    }
}
