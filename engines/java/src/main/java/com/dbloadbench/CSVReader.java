import java.util.*;

/**
 * Статические утилиты разбора CSV-строк.
 *
 * Раньше класс был ещё и in-memory ридером (грузил весь файл в
 * {@code List<String[]>}), что приводило к OutOfMemoryError на больших
 * объёмах. Потоковая часть переехала в {@link CSVStream}; здесь остались
 * только функции разбора одной строки и нормализации идентификаторов.
 */
public class CSVReader {

    /** Разбор одной CSV-строки по правилам RFC 4180 (с lenient-кавычками). */
    public static String[] parseCsvLine(String line) {
        List<String> fields = new ArrayList<>();
        StringBuilder current = new StringBuilder();
        boolean inQuotes = false;

        for (int i = 0; i < line.length(); i++) {
            char c = line.charAt(i);

            if (c == '"') {
                if (inQuotes && i + 1 < line.length() && line.charAt(i + 1) == '"') {
                    current.append('"');
                    i++;
                } else {
                    inQuotes = !inQuotes;
                }
            } else if (c == ',' && !inQuotes) {
                fields.add(current.toString());
                current.setLength(0);
            } else {
                current.append(c);
            }
        }
        fields.add(current.toString());

        return fields.toArray(new String[0]);
    }

    /** Удаляет обрамляющие кавычки/пробелы из идентификатора колонки/значения. */
    public static String cleanIdentifier(String s) {
        if (s == null) return "";
        while (true) {
            String stripped = s.trim()
                               .replaceAll("^\"|\"$", "")
                               .replaceAll("^`|`$", "")
                               .replaceAll("^'|'$", "")
                               .trim();
            if (stripped.equals(s)) break;
            s = stripped;
        }
        return s;
    }
}
