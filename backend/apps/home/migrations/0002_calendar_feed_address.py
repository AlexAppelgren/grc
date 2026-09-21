from django.db import migrations, models

from apps.shared.migration_helpers import split_policy_operations

"""home 0002 (HOM-04, D-52, ADR 0045): the calendar address takes the shape the decision
gave it, a month after 0001 declared the table from `schema.sql` §9.

The address moved from `/calendar/<token>` to `/calendar/feed.ics?token=<prefix>.<secret>`,
so the row changes with it:

- `token_prefix` is new and unique. It is the half of the address the fetch looks up, and
  it is unique across every bank because a calendar client presents no session and no key,
  so the row is found before any tenant is known.
- `token_hash` keeps the secret's SHA-256 and loses its unique index, which the prefix now
  carries. Two rows could only share a hash by sharing 256 random bits.
- `last_used_at` is new: the idle expiry reads it and a fetch stamps it.
- `filter` goes. Every subscription carries the same dates — the ones the outside world
  set — because the bank's own deadlines never reach a calendar outside the bank
  (ADR 0045, AC-TEN1), so two of its three values could never have meant anything.
- `calendar_feed` joins the identity-lookup clause as its fifth table, which is what lets
  the fetch read the row with no tenant activated. The clause is `FOR SELECT` only: the
  write rule stays the session's own zone, so nothing can be written through it (H15).

Adding a unique column to a table that already exists is safe here because the table is
empty everywhere: the four calendar-feed operations have answered 501 since the day they
were declared, so no code path has ever written a row.
"""


class Migration(migrations.Migration):

    dependencies = [
        ('home', '0001_home'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='calendarfeed',
            name='filter',
        ),
        migrations.AddField(
            model_name='calendarfeed',
            name='token_prefix',
            field=models.CharField(default='', max_length=16, unique=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='calendarfeed',
            name='last_used_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='calendarfeed',
            name='token_hash',
            field=models.CharField(max_length=64),
        ),
        *split_policy_operations("calendar_feed", identity_lookup=True),
    ]
