# Pipeline

Локальные инструменты производства «Үкі». Python 3.10+, Linux.

| Каталог | Назначение |
| --- | --- |
| `assets/` | Загрузка и проверка ресурсов Drive; [схема и команды](../assets/README.md) |
| `krita/export_reference_views.py` | Экспорт пяти групп v7 и общего листа внутри Krita 6; [инструкция](../characters/uki/references/poses/views-v7.md) |
| `krita/install_brushes.py` | Проверка/установка двух разрешённых кистей |
| `blender/` | [Сборка и проверка единого прототипа Үкі](blender/README.md); библиотеки сцен по #11 остаются отдельной работой |
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
