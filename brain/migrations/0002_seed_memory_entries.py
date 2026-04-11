from django.db import migrations


class Migration(migrations.Migration):
    """
    Seed migration — personal MemoryEntry seeds removed in the product fork
    (PR 1 strip-personal-layers). Kept at this number with an empty
    operations list so the migration chain stays linear; renumbering would
    require every environment with 0002 applied to re-squash.
    """

    dependencies = [
        ("brain", "0001_initial"),
    ]

    operations = []
