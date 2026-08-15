"""places and story_places

Revision ID: 0013
Revises: 0012

Where a story happens, so a later feature can ask "what is happening in
India" without re-reading every article.

Three kinds of place, not two. A country-or-GLOBAL split looks sufficient
until you tag the August 12 eclipse: it crossed Spain, France, the UK and
Ireland, which is EUROPE, not the same thing as a climate accord. Collapsing
regional into global would make "everywhere" the largest and least useful tag
in the table.

Region codes are all longer than two characters so they can never collide
with an ISO 3166-1 alpha-2 code -- the length of a code tells you its kind
without consulting this table.

The country list is CURATED, not the full ISO 249. That is a deliberate
trade: it is short enough to review, at the cost of a story about an unseeded
country losing its tag. worker.categorize prints every code it rejects so
that gap is visible rather than silent, and because code is the primary key,
filling one is an INSERT rather than a migration.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_REGIONS = [
    ("GLOBAL", "Global", "global"),
    ("EUROPE", "Europe", "region"),
    ("MIDEAST", "Middle East", "region"),
    ("AFRICA", "Africa", "region"),
    ("ASIA", "Asia", "region"),
    ("LATAM", "Latin America", "region"),
    ("NAMERICA", "North America", "region"),
    ("OCEANIA", "Oceania", "region"),
]

# Grouped by region for review, stored flat. Weighted towards what this
# corpus actually covers -- the largest outlets here are Indian, British and
# Australian -- while keeping every country that turns up in wire coverage.
_COUNTRIES = [
    # Europe
    ("GB", "United Kingdom"),
    ("IE", "Ireland"),
    ("FR", "France"),
    ("DE", "Germany"),
    ("ES", "Spain"),
    ("PT", "Portugal"),
    ("IT", "Italy"),
    ("NL", "Netherlands"),
    ("BE", "Belgium"),
    ("CH", "Switzerland"),
    ("AT", "Austria"),
    ("SE", "Sweden"),
    ("NO", "Norway"),
    ("DK", "Denmark"),
    ("FI", "Finland"),
    ("IS", "Iceland"),
    ("PL", "Poland"),
    ("CZ", "Czechia"),
    ("SK", "Slovakia"),
    ("HU", "Hungary"),
    ("RO", "Romania"),
    ("BG", "Bulgaria"),
    ("GR", "Greece"),
    ("HR", "Croatia"),
    ("RS", "Serbia"),
    ("SI", "Slovenia"),
    ("BA", "Bosnia and Herzegovina"),
    ("AL", "Albania"),
    ("UA", "Ukraine"),
    ("BY", "Belarus"),
    ("RU", "Russia"),
    ("MD", "Moldova"),
    ("EE", "Estonia"),
    ("LV", "Latvia"),
    ("LT", "Lithuania"),
    ("CY", "Cyprus"),
    ("MT", "Malta"),
    ("TR", "Turkey"),
    ("GE", "Georgia"),
    ("AM", "Armenia"),
    ("AZ", "Azerbaijan"),
    # Middle East
    ("IL", "Israel"),
    ("PS", "Palestine"),
    ("LB", "Lebanon"),
    ("SY", "Syria"),
    ("JO", "Jordan"),
    ("IQ", "Iraq"),
    ("IR", "Iran"),
    ("SA", "Saudi Arabia"),
    ("AE", "United Arab Emirates"),
    ("QA", "Qatar"),
    ("KW", "Kuwait"),
    ("BH", "Bahrain"),
    ("OM", "Oman"),
    ("YE", "Yemen"),
    # Asia
    ("CN", "China"),
    ("JP", "Japan"),
    ("KR", "South Korea"),
    ("KP", "North Korea"),
    ("TW", "Taiwan"),
    ("HK", "Hong Kong"),
    ("IN", "India"),
    ("PK", "Pakistan"),
    ("BD", "Bangladesh"),
    ("LK", "Sri Lanka"),
    ("NP", "Nepal"),
    ("AF", "Afghanistan"),
    ("TH", "Thailand"),
    ("VN", "Vietnam"),
    ("PH", "Philippines"),
    ("ID", "Indonesia"),
    ("MY", "Malaysia"),
    ("SG", "Singapore"),
    ("MM", "Myanmar"),
    ("KH", "Cambodia"),
    ("KZ", "Kazakhstan"),
    ("UZ", "Uzbekistan"),
    ("MN", "Mongolia"),
    # Africa
    ("EG", "Egypt"),
    ("LY", "Libya"),
    ("TN", "Tunisia"),
    ("DZ", "Algeria"),
    ("MA", "Morocco"),
    ("SD", "Sudan"),
    ("SS", "South Sudan"),
    ("ET", "Ethiopia"),
    ("ER", "Eritrea"),
    ("SO", "Somalia"),
    ("KE", "Kenya"),
    ("UG", "Uganda"),
    ("TZ", "Tanzania"),
    ("RW", "Rwanda"),
    ("NG", "Nigeria"),
    ("GH", "Ghana"),
    ("SN", "Senegal"),
    ("ML", "Mali"),
    ("CI", "Cote d'Ivoire"),
    ("CM", "Cameroon"),
    ("CD", "DR Congo"),
    ("ZA", "South Africa"),
    ("ZW", "Zimbabwe"),
    ("ZM", "Zambia"),
    ("MZ", "Mozambique"),
    ("AO", "Angola"),
    # Americas
    ("US", "United States"),
    ("CA", "Canada"),
    ("MX", "Mexico"),
    ("GT", "Guatemala"),
    ("HN", "Honduras"),
    ("SV", "El Salvador"),
    ("NI", "Nicaragua"),
    ("CR", "Costa Rica"),
    ("PA", "Panama"),
    ("CU", "Cuba"),
    ("HT", "Haiti"),
    ("DO", "Dominican Republic"),
    ("JM", "Jamaica"),
    ("CO", "Colombia"),
    ("VE", "Venezuela"),
    ("EC", "Ecuador"),
    ("PE", "Peru"),
    ("BO", "Bolivia"),
    ("BR", "Brazil"),
    ("CL", "Chile"),
    ("AR", "Argentina"),
    ("UY", "Uruguay"),
    ("PY", "Paraguay"),
    # Oceania
    ("AU", "Australia"),
    ("NZ", "New Zealand"),
    ("PG", "Papua New Guinea"),
    ("FJ", "Fiji"),
]


def upgrade() -> None:
    op.create_table(
        "places",
        # 8, not 2: region codes share this table and are longer.
        sa.Column("code", sa.String(8), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        # 'country' | 'region' | 'global'
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
    )

    op.create_table(
        "story_places",
        # CASCADE for the same reason story_categories has it: a tag is
        # derived data that merge_pass may delete without asking anyone.
        sa.Column(
            "story_id",
            UUID(as_uuid=False),
            sa.ForeignKey("stories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "place_code",
            sa.String(8),
            sa.ForeignKey("places.code"),
            primary_key=True,
        ),
        sa.Column("rank", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # The PK index leads with story_id, which serves "places for this story".
    # Filtering a place needs the other order.
    op.create_index("ix_story_places_code", "story_places", ["place_code", "story_id"])

    rows = [
        {"code": c, "name": n, "kind": k, "sort_order": i}
        for i, (c, n, k) in enumerate(_REGIONS, start=1)
    ] + [
        {"code": c, "name": n, "kind": "country", "sort_order": i}
        for i, (c, n) in enumerate(_COUNTRIES, start=len(_REGIONS) + 1)
    ]
    op.bulk_insert(
        sa.table(
            "places",
            sa.column("code", sa.String),
            sa.column("name", sa.String),
            sa.column("kind", sa.String),
            sa.column("sort_order", sa.SmallInteger),
        ),
        rows,
    )

    # Alembic-created tables do not inherit RLS, and Supabase grants anon full
    # DML on public by default -- so this is what actually keeps them locked.
    op.execute("alter table places enable row level security")
    op.execute("alter table story_places enable row level security")


def downgrade() -> None:
    op.drop_index("ix_story_places_code", table_name="story_places")
    op.drop_table("story_places")
    op.drop_table("places")
