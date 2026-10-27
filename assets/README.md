# Внешние ресурсы и Asset Sync

Google Drive хранит бинарные оригиналы, генерации, экспорты, кисти, Blender-файлы
и видео. GitHub хранит код, Markdown и конфигурации, включая `manifest.yaml`.
Git LFS не используется. Локальные файлы — `.local-assets/`, результаты —
`output/`; обе папки игнорируются Git.

## Установка и команды

Linux, Python 3.10+. Выполнять из корня клона:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-assets.txt
.venv/bin/python -m pipeline.assets list
.venv/bin/python -m pipeline.assets sync --character uki --credentials .secrets/drive-user.json
.venv/bin/python -m pipeline.assets verify --episode ep01
```

Приватные файлы скачиваются через авторизованный Google Drive API
`files.get?alt=media`, с областью `drive.readonly`. Поддерживаются локальные JSON
Google Auth типов `authorized_user` (OAuth с refresh token) и `service_account`.
Аккаунт должен иметь доступ к файлам. Путь можно передать через
`UKI_GOOGLE_CREDENTIALS`. Credentials и токены не печатаются и не публикуются;
хранить их в `.secrets/`. OAuth client secret сам по себе не является готовыми
credentials: сначала авторизовать свой клиент и получить пользовательский
refresh token. Service account требует предоставления ему доступа на Drive.
CLI не меняет sharing и не записывает credentials обратно на диск.

Фильтры `--id` (повторяемый), `--character`, `--episode`, `--scene` объединяются
через «И». Примеры:

```bash
.venv/bin/python -m pipeline.assets sync --id uki.poses.v7 --credentials .secrets/drive-user.json
.venv/bin/python -m pipeline.assets list --episode ep01 --scene sc04
```

Вторая команда пока выдаст ошибку отсутствия ресурсов: реальные Drive IDs
сцен 00/04 ещё не зарегистрированы (#9). Общие референсы не являются сюжетными
сценами. Тег `episodes` означает использование ресурса, а не дублирование.

`--manifest PATH` указывается **перед подкомандой**. Манифест размещается
в `<корень>/assets/`; кэш определяется как `<корень>/.local-assets/`.

## Схема v1

| Поле | Назначение |
| --- | --- |
| `schema_version` | Целое `1`, на уровне документа |
| `assets` | Список записей |
| `id` | Уникальный ID: строчные латинские буквы, цифры, `._-` |
| `source` | Только `google_drive` |
| `drive_file_id` | Проверенный ID фактического файла |
| `path` | Путь относительно `.local-assets/`, с оригинальным именем |
| `kind`, `purpose` | Тип и назначение |
| `status` | Производственный/авторский статус, например `accepted_static` |
| `version` | Явная строка версии |
| `sha256` | SHA-256 полученных байтов; `null` до проверки блокирует sync/import |
| `size_bytes` | Реальный размер, положительное целое или `null` |
| `characters`, `episodes`, `scenes` | Списки тегов для фильтров, по умолчанию `[]` |
| `author`, `original_name`, `drive_modified_time`, `verified_on`, `provenance`, `license`, `verification` | Дополнительные сведения о происхождении/проверке |

Дубли ключей YAML, ID и целевых путей, абсолютные пути, `..`, скрытые компоненты,
Windows-разделители и symlink в кэше отклоняются. Инструмент скачивает обычные
файлы; экспорт нативных Google Docs/Slides/Sheets не входит в его назначение.

Пример ниже **не пригоден для скачивания**, в рабочий манифест не включён.
Placeholders заменяются после проверки фактического файла:

```yaml
schema_version: 1
assets:
  - id: example.scene-source
    source: google_drive
    drive_file_id: '<REAL_DRIVE_FILE_ID>'
    path: episodes/ep01/sc00/krita/<ORIGINAL_NAME>.kra
    kind: krita_source
    purpose: 'Исходник сцены 00 — пример'
    status: awaiting_verification
    version: '<REAL_VERSION>'
    sha256: null
    size_bytes: null
    characters: [uki]
    episodes: [ep01]
    scenes: [sc00]
```

## Первое получение через подключённый Drive

Авторизация подключённого к Codex Drive не передаётся локальному CLI.
Проверить метаданные, скачать оригинал через connector, материализовать
возвращённый authenticated file reference в локальный файл. Временные ссылки
скачивания в Git не сохранять. Проверить содержимое, вычислить `sha256sum`,
внести реальные хеш/размер/версию в манифест. Затем принять файл через CLI:

```bash
.venv/bin/python -m pipeline.assets import --id uki.poses.v7 --file /tmp/uki_five_views_brush_cleanup_v7.kra
```

27.10.2026 через авторизованный connector действительно получены KRA v7 и два
ZIP кистей. Хеши в манифесте вычислены по локальным байтам. `verify` проверяет
их без сети. Сетевой путь CLI с отдельными credentials проверен моками;
реальное скачивание в этой работе выполнено через connector.

## Сохранность и версии

Скачивание идёт во временный файл, затем проверяются SHA-256 и размер.
При ошибке временный файл удаляется; результат публикуется атомарно, без
перезаписи существующего файла. Параллельные CLI используют Linux `flock`.

Повторный sync проверяет локальные байты и не обращается к сети, если хеш
совпадает. Он не ищет новую редакцию на Drive: закреплённая локальная версия
остаётся воспроизводимой. При загрузке в пустой кэш изменившиеся байты
на том же Drive ID отклоняются по хешу.

При локальных изменениях или другой версии по существующему пути — ошибка
с сохранением файла. Автоматического `--force` нет. Сначала сохранить рабочую
копию и оригинал; новую редакцию зарегистрировать отдельными ID, версией и
путём после проверки. Не менять SHA-256 лишь для обхода ошибки.

Перед Blender-сборкой выполнить `sync`, затем `verify`. Подключать файлы по
относительным путям внутри клона. Экспорты слоёв создавать отдельно от KRA
и первичных генераций, документировать ID/версию источника и параметры.
Для переноса между машинами сохранить производные файлы на Drive и включить
в манифест; в GitHub экспорты не отправлять.

## Проверки

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pipeline.assets verify --character uki
.venv/bin/python -m pipeline.krita.install_brushes
```

Тесты работают без сети и реальной авторизации: манифест, пути, symlink,
хеш/размер, повторный sync, ошибки доступа/сети, смена версии, локальные
изменения, гонка публикации, импорт connector-файла и установка кистей.

API: [Drive downloads](https://developers.google.com/workspace/drive/api/guides/manage-downloads),
[Google Auth credentials](https://google-auth.readthedocs.io/en/latest/reference/google.auth.html).
