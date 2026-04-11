# Projects App

Reusable Django app that adds a lightweight project-management REST API:

- `Project`
- `Section`
- `Task`
- `TaskComment`

No templates, no JavaScript, no NockCC-specific imports.

## Install

1. Add the app and DRF to `INSTALLED_APPS`.
2. Include the URL patterns.
3. Run migrations.

```python
# settings.py
INSTALLED_APPS = [
    ...
    "rest_framework",
    "projects",
]
```

```python
# urls.py
from django.urls import include, path

urlpatterns = [
    ...
    path("", include("projects.urls")),
]
```

```bash
python manage.py migrate
```

## Endpoints

- `GET|POST /api/projects/`
- `GET|PUT|DELETE /api/projects/<slug>/`
- `GET|POST /api/projects/<slug>/sections/`
- `PUT|DELETE /api/sections/<id>/`
- `POST /api/sections/<id>/reorder/`
- `GET|POST /api/tasks/`
- `GET|PUT|DELETE /api/tasks/<id>/`
- `POST /api/tasks/<id>/complete/`
- `POST /api/tasks/<id>/reopen/`
- `POST /api/tasks/<id>/move/`
- `GET|POST /api/tasks/<id>/comments/`
- `DELETE /api/comments/<id>/`
- `GET /api/tasks/dashboard/`
- `GET /api/tasks/overdue/`
- `GET /api/tasks/today/`
- `GET /api/tasks/upcoming/`

## Optional Settings

```python
PROJECTS_MAX_TASKS_PER_PROJECT = 0
PROJECTS_DEFAULT_PRIORITY = "medium"
PROJECTS_DEFAULT_STATUS = "todo"
```

## Management Commands

```bash
python manage.py import_from_asana --token <ASANA_PAT> --workspace <WORKSPACE_GID>
python manage.py import_from_asana --token <ASANA_PAT> --workspace <WORKSPACE_GID> --project <PROJECT_GID>
python manage.py task_stats
```

## Test

```bash
python manage.py test projects
```

## NockCC Note

This app is intentionally standalone, but the current NockCC repo already mounts an existing Asana API under `/api/tasks/`.
If you install `projects` into this repo at the root URLConf, those task routes will conflict.
Use a host-specific prefix or separate URLConf when integrating it into the current NockCC monolith.
