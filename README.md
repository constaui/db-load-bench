# DB Load Bench

Инструмент для тестирования баз данных с графическим интерфейсом, написанным с помощью библиотеки PyQt6, и реализациями на 4 языках-движках (Python, Rust, Go, Java) и для 2 СУБД (MySQL, PostgreSQL). Программма предназначена для оценки производительности операций вставки данных большого объема в базы данных.

При необходимости можно добавить реализации движков на других языках и для других СУБД.

## Структура проекта

```
db-load-bench/
├── main.py              # Точка входа с графическим интерфейсом
├── engines/             # Движки со способами вставки
│   ├── rust/
│   ├── python/
│   ├── go/
│   └── java/
├── orchestrator/        # Управление процессами запуска движков
├── src/                 # Основная работа с БД и графический интерфейс
└── .env.example         # Шаблон .env файла
```

## Требования

- Python 3.8+ - [python.org](https://www.python.org/)
- Rust (for Rust engine) - [rustup.rs](https://rustup.rs/)
- Go 1.22+ (for Go engine) - [golang.org](https://golang.org/)
- Java 17+ & Maven (for Java engine) - [maven.apache.org](https://maven.apache.org/)
- MySQL [dev.mysql.com](https://dev.mysql.com/doc/mysql-getting-started/en/)
- PostgreSQL [postgresql.org](https://www.postgresql.org/)

## Установка

### 1. Склонируйте репозиторий и перейдите в папку

```bash
cd db-load-bench
```

### 2. Настройка окружения Python

Создайте и активируйте виртуальное окружение:

```bash
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# или
.venv\Scripts\activate     # Windows
```

Установите зависимости:

```bash
pip install -r requirements.txt
```

### 3. Настройка окружения

Скопируйте пример .env файла (.env.example) и допишите параметры подключения к базам данных:

```bash
cp .env.example .env
```

### 4. Настройка Rust

Скомпилируйте Rust движок:

```bash
cd engines/rust
cargo build --release
```

### 5. Настройка Go

Скомпилируйте Go движок

```bash
cd engines/go
go build -o insert_engine
```

### 6. Настройка Java

Скомпилируйте Java движок:

```bash
cd engines/java
chmod +x build.sh
./build.sh
# или напрямую:
mvn -q package -DskipTests
```

## Запуск приложения

Запустите графический интерфейс:

```bash
python main.py
```

---

## Командная строка для движков

Все движки имеют одинаковый интерфейс командной строки:

| Опция          | Описание                                                      | По умолчанию     |
| -------------- | ------------------------------------------------------------- | ---------------- |
| `--method`     | Метод вставки: `default_insert`, `bulk_insert`, `file_insert` | `default_insert` |
| `--csv`        | Путь к .csv файлу (**required**)                              | -                |
| `--table`      | Имя таблицы для вставки                                       | `Test`           |
| `--db-type`    | Тип базы данных: `mysql`, `postgresql`                        | `mysql`          |
| `--host`       | Хост базы данных                                              | `localhost`      |
| `--port`       | Порт базы данных                                              | `3306`           |
| `--user`       | Имя пользователя базы данных                                  | -                |
| `--password`   | Пароль базы данных                                            | -                |
| `--database`   | Название базы данных                                          | -                |
| `--batch-size` | Размер батча для bulk-вставки                                 | `1000`           |

## Примеры

**MySQL bulk insert (Rust):**

```bash
cd engines/rust
cargo run --release -- \
  --csv data.csv \
  --table users \
  --db-type mysql \
  --host localhost \
  --port 3306 \
  --user root \
  --password secret \
  --database benchmark \
  --method bulk_insert \
  --batch-size 5000
```

**PostgreSQL default insert (Go):**

```bash
cd engines/go
go run . \
  --csv data.csv \
  --table users \
  --db-type postgresql \
  --host localhost \
  --port 5432 \
  --user postgres \
  --password secret \
  --database benchmark \
  --method default_insert
```

**MySQL bulk insert (Java):**

```bash
cd engines/java
java -jar target/insert_engine.jar \
  --csv data.csv \
  --table users \
  --db-type mysql \
  --host localhost \
  --port 3306 \
  --user root \
  --password secret \
  --database benchmark \
  --method bulk_insert \
  --batch-size 5000
```

---

## Формат CSV файла

CSV файл должен иметь первую строку с заголовочными полями. Заголовочные поля используются к качестве полей таблицы.

```csv
id,name,email,age
1,Иван Иванов,ivan@example.com,30
2,Ольга Иванова,olga@example.com,25
```

## Результат

Результат запуска теста хранится в следующем формате:

```json
[
  {
    "engine": "Rust",
    "db_type": "mysql",
    "method": "bulk_insert",
    "experiment_config": { "rows": 10000 },
    "method_config": { "batch_size": 1000 },
    "metrics": { "elapsed": 2.345678, "rps": 4263.2 }
  },
  ...
]
```
