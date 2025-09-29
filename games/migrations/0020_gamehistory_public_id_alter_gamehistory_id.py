import uuid
from django.db import migrations, models

def generate_public_ids(apps, schema_editor):
    GameHistory = apps.get_model('games', 'GameHistory')
    for gh in GameHistory.objects.filter(public_id__isnull=True):
        gh.public_id = uuid.uuid4()
        gh.save(update_fields=['public_id'])

class Migration(migrations.Migration):

    dependencies = [
        ("games", "0019_alter_gamehistory_decrypted_winning_numbers"),
    ]

    operations = [
        # 1) Add the field as nullable first
        migrations.AddField(
            model_name="gamehistory",
            name="public_id",
            field=models.UUIDField(default=None, editable=False, null=True),
        ),

        # 2) Populate unique values for all existing rows
        migrations.RunPython(generate_public_ids),

        # 3) Alter the field: make it non-nullable and unique
        migrations.AlterField(
            model_name="gamehistory",
            name="public_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
