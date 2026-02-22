# Bulletin Format Notes

## Output Documents
The tool generates **4 documents** per Sunday from the same S&S data:

| # | Document | Description | Paper | Layout |
|---|----------|-------------|-------|--------|
| 1 | **Bulletin for Congregation** | Main worship bulletin with notation images | Legal (8.5×14) saddle-stitched booklet | Two-column |
| 2 | **Full with Hymns LARGE PRINT** | Vision-accessible version, all text, full hymn lyrics | Letter (8.5×11) | Single-column, large font |
| 3 | **Pulpit Scripture** | Readings + psalm for scripture reader volunteer | Letter (8.5×11), front/back | Two-column, large font |
| 4 | **Pulpit Prayers** | Creed + prayers of intercession for prayer leader | Letter (8.5×11), front/back | Two-column, large font |

### Generation Order
1. **Bulletin for Congregation** — generated first (determines page numbers)
2. **Pulpit Scripture** — independent, can generate in parallel with prayers
3. **Pulpit Prayers** — needs creed page number from step 1 (auto-fills "Please turn to page ___ of your Bulletin")
4. **Full with Hymns LARGE PRINT** — independent

### Hymn Handling by Document

| Hymn Slot | Standard Bulletin | Large Print | Why |
|-----------|------------------|-------------|-----|
| Gathering | **Title only** (e.g., "ELW 335") | **Full text lyrics** with verses | Congregation has hymnals for standard; large print users can't use hymnal |
| Sermon | **Title only** | **Full text lyrics** with verses | Same reason |
| Offertory | **Notation image** (always "Oh, come, Lord Jesus") | **Text lyrics** (no notation) | Fixed hymn, always the same |
| Communion | **Notation image** (from S&S) | **Text lyrics** (from S&S words download) | People can't juggle hymnal during communion |
| Sending | **Title only** | **Full text lyrics** with verses | Same as gathering/sermon |

S&S data needed per hymn:
- Standard bulletin: only **communion hymn** needs notation image download (melody_atom_id)
- Large print: all hymns need **text lyrics** download (words_atom_id) + copyright info

## Standard Bulletin Overview (from Feb 22, 2026 Lent 1A)
- 14 pages (12 liturgy + 2 announcements/info)
- Pages 1-12: worship service content
- Pages 13-14: announcements insert (manual, not automated)
- Two-column layout for readings, psalms, confession, creed, prayers
- Single-column for some sections (intro text, prayer of the day)

## Formatting Conventions
- **Section headings:** ALL CAPS, bold, black (e.g., "GATHERING CHIMES: WORSHIP BEGINS")
- **`*` prefix:** Indicates congregation stands (e.g., "*CONFESSION AND FORGIVENESS")
- **"Pastor:" / "P:"** in red, bold — marks pastor's spoken parts
- **"C:" / "CONGREGATION:"** — congregation response label
- **Bold text** — congregation's spoken/sung responses
- **Red italic** — rubrics/instructions (e.g., *"All may make the sign of the cross..."*)
- **Red text** — role labels ("Pastor", "Scripture Reader", "Communion Assistant", "Prayer Leader")
- **Red ☩ symbol** — liturgical cross
- **Superscript numbers** — verse numbers in readings
- **"LORD" in small caps** — per NRSV convention

## Page-by-Page Structure

### Page 1 — Cover
- Church name: "Ascension Lutheran Church" (large, bold)
- Address: 6481 Old Canton Road Jackson · Mississippi · 39211 · 601.956.4263
- Website + email
- Church logo (cross with water/river imagery)
- Service time: "10:00 AM — February 22, 2026"
- Liturgical day: "The First Sunday in Lent" (large, bold)

### Page 2 — Opening
- Welcome message (small text)
- Standing/bold notation key
- GATHERING CHIMES
- CHORAL CALL TO WORSHIP (title + composer)
- PRELUDE (title + performer)
- WELCOME
- *CONFESSION AND FORGIVENESS (two-column for congregation parts)

### Page 3 — Lent Invitation + Prayer of the Day + First Reading begins
- *INVITATION TO LENT (two-column)
- *PRAYER OF THE DAY (single-column, bold "Amen.")
- FIRST READING: GENESIS 2:15-17; 3:1-7 (with "Scripture Reader" in red)
- Reading intro in italic
- Reading text in two columns

### Pages 4 — Psalm + Second Reading begins
- "The word of the Lord." / "Thanks be to God." (response after reading)
- PSALM 32 (with "The Congregation reads responsively" in red italic)
- Congregation verses in bold, alternating with regular
- SECOND READING continues

### Page 5 — Second Reading continues + Gospel Acclamation
- "The word of the Lord." / "Thanks be to God."
- *GOSPEL ACCLAMATION — **notation image** (melody line with lyrics)

### Page 6 — Gospel + Sermon Hymn + Creed begins
- *GOSPEL: MATTHEW 4:1-11 (with intro italic)
- "Pastor:" announces gospel; response: "Glory to You, O Lord."
- Gospel text in two columns
- "This is the gospel of our Lord." / "Praise to you, O Christ."
- *Congregation is seated* (rubric in red italic)
- SERMON
- *SERMON HYMN: ELW 319 (title only, no notation in this version)
- *NICENE CREED (bold, two-column)

### Page 7 — Creed continues + Peace + Offering + Hymn notation
- *PRAYERS OF INTERCESSION (with petition response pattern)
- *SHARING OF THE PEACE
- OFFERING
- OFFERTORY
- *HYMN — **notation image** (offertory hymn with melody)

### Page 8 — Offering Prayer + Great Thanksgiving
- *OFFERING PRAYER
- *GREAT THANKSGIVING — **notation image** (call and response melody)
- Preface text

### Page 9 — Holy Holy Holy + Eucharistic Prayer
- **Notation image** — Sanctus ("Holy, holy, holy Lord...")
- *EUCHARISTIC PRAYER (two-column)
- Words of institution

### Page 10 — Lord's Prayer + Communion + Agnus Dei
- *LORD'S PRAYER (bold, two-column)
- *INVITATION TO COMMUNION
- ANGUS DEI — **notation image**

### Page 11 — Communion Hymn + Post-Communion
- COMMUNION HYMN: ELW 512 — **notation image** (full hymn with melody)
- Post-communion blessing
- **Notation image** — Nunc Dimittis ("Now, Lord, you let your servant go...")

### Page 12 — Prayer After Communion + Blessing + Sending
- **Notation image** continues (Nunc Dimittis)
- *PRAYER AFTER COMMUNION
- *BLESSING
- ANNOUNCEMENTS (with notation image continuing)
- *SENDING HYMN: ELW 333 (title only)
- SENDING dismissal
- *POSTLUDE (title + performer)
- Copyright/license block at bottom

### Pages 13-14 — Announcements Insert (MANUAL)
- Worship assistants + leaders info
- This week's schedule
- Looking ahead
- About today's music
- Various announcements with graphics
- QR codes

## Music Notation Images in Bulletin
These are embedded as images (not text). From S&S these are:
1. Gospel Acclamation (p5)
2. Offertory hymn (p7-8)
3. Great Thanksgiving dialog (p8)
4. Sanctus / Holy Holy Holy (p9)
5. Agnus Dei / Lamb of God (p10-11)
6. Communion hymn (p11)
7. Nunc Dimittis / Song of Simeon (p11-12)

## Hymns Referenced (this bulletin)
- ELW 335 — Jesus, Keep Me Near the Cross (Gathering, title only)
- ELW 319 — O Lord, Throughout These Forty Days (Sermon hymn, title only)
- Offertory hymn — notation embedded (not ELW number shown)
- ELW 512 — Lord, Let My Heart Be Good Soil (Communion, notation embedded)
- ELW 333 — Jesus Is a Rock in a Weary Land (Sending, title only)

## Seasonal Variations (from cross-season analysis)

### Confession and Forgiveness
| Season | Form |
|--------|------|
| Pentecost / Ordinary Time | **Form A** — "God of all mercy and consolation..." / "We confess that we are captive to sin..." |
| Advent, Christmas, Epiphany | **Form B** — "Blessed be the holy Trinity, one God..." / Two rounds of confession |
| Lent | **Invitation to Lent** replaces standard confession (unique seasonal text) |
| Christmas Eve | **Omitted** — replaced by "Declaration of Good News" narrative |

### Canticle of Praise
| Season | Canticle |
|--------|----------|
| Pentecost / Ordinary Time | **Glory to God** (S-139) |
| Advent | **Glory to God** (S-139) |
| Christmas / Epiphany | **This Is the Feast** (S-140/S-141) |
| Lent | **Omitted** (Lent drops the canticle of praise) |
| Christmas Eve | **Omitted** |

### Gospel Acclamation
| Season | Acclamation |
|--------|-------------|
| Ordinary Time, Epiphany, Easter | **Alleluia** (S-142) + "Lord, to whom shall we go?" |
| Advent | **ELW 262 "Wait for the Lord"** (Taizé — no Alleluia) |
| Lent | **"Return to the Lord"** (Lenten verse — no Alleluia) |
| Christmas Eve | Seasonal hymn text (e.g., "What child is this") |

### Creed
| Season | Creed |
|--------|-------|
| Pentecost / Ordinary Time | Apostles Creed |
| Advent, Christmas, Epiphany | Apostles Creed |
| Lent, Easter | **Nicene Creed** |
| Christmas Eve | Apostles Creed |
Note: User selects creed — the above is the typical pattern but pastor may override.

### Eucharistic Prayer
| Season | Form |
|--------|------|
| Pentecost / Ordinary Time | **Short form** — Words of Institution only |
| Advent | **Poetic/literary form** — "Holy One, the beginning and the end..." |
| Christmas / Epiphany | **Extended form** — "You are indeed holy..." with Memorial Acclamation + sung Amen |
| Lent | **Extended form** with Memorial Acclamation (similar to Christmas/Epiphany) |

### Prayers of Intercession Response
Changes every week. Examples seen:
- "God of grace, hear our prayer."
- "God of grace, receive our prayer."
- "Hear us, O God, / Your mercy is great."
- "Merciful God, receive our prayer."
- "God, in your mercy, receive our prayer."

### Sending Dismissal
Usually: "Go in peace to love and serve the Lord." / "Thanks be to God."
Christmas Eve: "Go in peace. Share the light of Christ."

### Musical Setting (ELW Setting 3 — consistent)
All regular services use ELW Setting 3:
- Kyrie: S-138
- Glory to God: S-139
- This Is the Feast: S-140/S-141
- Gospel Acclamation (Alleluia): S-142
- Great Thanksgiving: S-144
- Sanctus: S-144
- Agnus Dei: S-146
- Nunc Dimittis: S-147

### Christmas Eve — Major Outlier
Drops: Kyrie, Canticle, standard Sanctus, Agnus Dei, Nunc Dimittis.
Unique: Declaration of Good News, candle-lighting, children's message, reduced readings.

## What Changes Week to Week
- Cover date and liturgical day name
- Confession and Forgiveness text (varies by season — see above)
- Canticle of Praise (varies by season — see above)
- Prayer of the Day
- Readings (First, Psalm, Second, Gospel)
- Gospel Acclamation (varies by season — see above)
- Creed (Apostles vs Nicene — see above)
- Hymn selections (gathering, sermon, communion, sending)
- Eucharistic Prayer form (varies by season — see above)
- Prayers of Intercession (text + response change weekly)
- Announcements insert (completely manual)

## What Stays the Same
- Cover layout, logo, church info
- Welcome message
- Service order structure
- Musical setting (ELW Setting 3 throughout)
- Offertory hymn: "Oh, come, Lord Jesus, be our guest" (consistent)
- Lord's Prayer text (spoken, traditional "trespasses" form)
- Great Thanksgiving dialogue melody (Setting 3 S-144)
- Sanctus, Agnus Dei, Nunc Dimittis notation images (Setting 3)
- Kyrie notation image (Setting 3, present in all regular services)
- Blessing: Aaronic ("The Lord bless you and keep you...")
- Invitation to Communion: "Taste and see that the Lord is good"
- Sending: "Go in peace to love and serve the Lord."
- Copyright block

---

## Full with Hymns LARGE PRINT Format

### Key Differences from Standard Bulletin
- **Single-column layout** throughout (no two-column text)
- **Larger font** across the board
- **All text, no notation images** — everything rendered as text (one exception: Gospel Acclamation still has notation image)
- **Section headings** use gray background bars instead of just bold caps
- **Role labels** ("Scripture Reader", "Prayer Leader", "Pastor", "Congregation") in red, right-aligned on heading bars
- **"Large Print Booklet"** banner on cover
- **~16 pages** (longer due to larger font + full hymn lyrics)
- Same liturgical content as standard bulletin, just formatted differently

### What's Different in Large Print vs Standard
| Element | Standard Bulletin | Large Print |
|---------|------------------|-------------|
| Hymns (gathering, sermon, sending) | Title + ELW number only | Full verse lyrics as text, two-column, with copyright |
| Communion hymn | Notation image | Text lyrics, two-column, with copyright |
| Offertory hymn | Notation image | Text lyrics, two-column |
| Great Thanksgiving | Notation image (sung dialog) | Text only — P:/C: spoken dialog format |
| Sanctus | Notation image | Bold text: "Holy, holy, holy Lord..." |
| Agnus Dei | Notation image | Bold text: "Lamb of God, you take away..." |
| Nunc Dimittis | Notation image | Bold text: "Now, Lord, you let your servant go in peace..." |
| Kyrie / Canticle of Praise | Notation images | Omitted entirely |
| Gospel Acclamation | Notation image | **Still notation image** (only exception) |
| Layout | Two-column for readings, etc. | Single-column throughout |
| Announcements | Pages 13-14 insert | Included as last pages (with graphics) |

---

## Pulpit Scripture Format

### Overview
- 2 pages (front/back of one sheet), 8.5×11 letter
- Title: "SCRIPTURE Readings – [Date]" with "Leader:" label top-right
- Yellow-highlighted "FRONT PAGE" / "BACK PAGE" labels
- Yellow-highlighted section headers for each reading

### Content
1. **FIRST READING** — yellow heading with citation (e.g., "Genesis 2:15-17; 3:1-7")
   - Intro: "A reading from THE BOOK OF [BOOK NAME]:"
   - Full reading text, large font, two-column
   - Closing: "The Word of the Lord." / "Thanks be to God."
2. **PSALM** — yellow heading
   - "Please read with me responsively"
   - Full psalm text, verse numbers, congregation bold alternating
3. **SECOND READING** — yellow heading with citation
   - Intro: "A reading from [BOOK NAME]"
   - Full reading text, two-column
   - Closing: "The word of the Lord." / **"Thanks be to God."**
4. End instruction: "Please rise in BODY or SPIRIT for the reading of the Gospel."
5. Recycle note: "Reader: Please take this script from the Pulpit to recycle when you leave"

---

## Pulpit Prayers Format

### Overview
- 2 pages (front/back of one sheet), 8.5×11 letter
- Title: "CREED & PRAYERS – [Date]" with "Leader:" label top-right
- Yellow-highlighted "FRONT PAGE" / "BACK PAGE" labels
- Yellow-highlighted section headers

### Content
1. **CREED** — yellow heading (e.g., "APOSTLES CREED" or "NICENE CREED")
   - Instruction: "Please turn to page **[N]** of your Bulletin and let us profess our faith using the words of the [NICENE/APOSTLES] Creed:"
   - **Page number auto-filled** from bulletin generation (step 1)
   - Full creed text, large font, two-column
2. **PRAYERS of INTERCESSION** — yellow heading
   - Intro: "We continue with the prayers of the people:"
   - Each petition paragraph followed by "Hear us, O God."
   - Bold congregation response: **"Your mercy is great."** (varies weekly)
   - Healing petition includes blank lines for handwritten names
   - Closing: "Receive our prayers, O God, through Jesus Christ, our strength and salvation."
   - "Amen."
3. End instruction (yellow-highlighted): "Leader: Please descend from the Pulpit, stepping aside for Pastor to rise at the Pulpit to share His Peace"
