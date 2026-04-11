from django.db import migrations


class Migration(migrations.Migration):
    """
    Seed migration — personal continuity entries removed in the product
    fork (PR 1 strip-personal-layers). Kept at this number with an empty
    operations list so the migration chain stays linear; renumbering would
    require every environment with 0004 applied to re-squash.
    """

    dependencies = [
        ("brain", "0003_add_continuity_and_consolidation_log"),
    ]

    operations = []
