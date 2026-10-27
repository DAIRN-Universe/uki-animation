# Pipeline

Локальные инструменты производства «Үкі». Python 3.10+, Linux.

| Каталог | Назначение |
| --- | --- |
| `assets/` | Загрузка и проверка ресурсов Drive; [схема и команды](../assets/README.md) |
| `krita/install_brushes.py` | Проверка/установка двух разрешённых кистей |
| `blender/` | Место будущих инструментов библиотек ресурсов, Actions и сцен |
| `render/` | Место будущих инструментов рендера |
| `../tests/` | Проверки без внешней сети |

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-assets.txt
.venv/bin/python -m pipeline.assets list
.venv/bin/python -m pipeline.assets sync --character uki --credentials .secrets/drive-user.json
.venv/bin/python -m pipeline.assets verify --character uki
.venv/bin/python -m pipeline.krita.install_brushes
.venv/bin/python -m unittest discover -s tests -v
```

Установка кистей по умолчанию только показывает действия. Для записи добавить
`--install`, затем перезапустить **Krita 6**. [Проверка KRA и кистей](../characters/uki/references/poses/README.md).

Бинарные ресурсы — Drive / `.local-assets/`, результаты — `output/`. В Git —
код, документация и манифесты. Исходники автоматически не изменяются.
[Правила ресурсов](../docs/assets-guide.md), [процесс](../docs/production-pipeline.md).
Лицензии кода и художественных материалов утверждаются раздельно.
