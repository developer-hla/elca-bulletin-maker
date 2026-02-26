"""Fixed liturgical texts used in document generation.

Texts that S&S does NOT provide (confirmed via investigation):
Kyrie, Canticle of Praise, Great Thanksgiving dialog, Sanctus,
Agnus Dei, Nunc Dimittis, Lord's Prayer, Offertory Hymn.

S&S DOES provide: Confession, Prayer of Day, Readings, Gospel Acclamation,
Prayers, Offering Prayer, Invitation to Communion, Prayer After Communion,
Blessing, Dismissal.
"""

from __future__ import annotations

from bulletin_maker.renderer.text_utils import DialogRole

# ── Liturgical / typographic symbols ──────────────────────────────────
CROSS = "\u2629"       # ✩  sign of the cross
MIDDOT = "\u00b7"      # ·  address separator
NBSP = "\u00a0"        #    non-breaking space
APOSTROPHE = "\u2019"        # '  curly apostrophe / right single quote
EMDASH = "\u2014"      # —  em dash
LQUOTE = "\u201c"      # "  left double quote
RQUOTE = "\u201d"      # "  right double quote

NICENE_CREED = (
    "We believe in one God, \n"
    "the Father, the Almighty,\n"
    "maker of heaven and earth,\n"
    "of all that is, seen and unseen.\n"
    "\n"
    "We believe in one Lord, \n"
    "Jesus Christ, the only \n"
    "Son of God, eternally begotten of the Father,\n"
    "God from God, \n"
    "Light from Light,\n"
    "true God from true God,\n"
    "begotten, not made,\n"
    "of one Being with the Father;\n"
    "\n"
    "Through him \n"
    "all things were made.\n"
    "For us and for our salvation\n"
    "he came down from heaven,\n"
    "was incarnate of the Holy Spirit\n"
    "and the virgin Mary\n"
    "and became truly human.\n"
    "\n"
    "For our sake he was crucified \n"
    "under Pontius Pilate;\n"
    "he suffered death \n"
    "and was buried.\n"
    "\n"
    "On the third day he rose again in accordance with \n"
    "the scriptures; \n"
    "he ascended into heaven \n"
    "and is seated at the right hand of the Father.\n"
    "\n"
    "He will come again in glory \n"
    "to judge the living and the dead, "
    "and his kingdom will have no end.\n"
    "\n"
    "We believe in the Holy Spirit, \n"
    "the Lord, the giver of life,\n"
    "who proceeds from \n"
    "the Father and the Son,\n"
    "who with the Father and the Son\n"
    "is worshiped and glorified,\n"
    "who has spoken through the prophets.\n"
    "\n"
    "We believe in one holy catholic and apostolic church.\n"
    "\n"
    "We acknowledge one baptism \n"
    "for the forgiveness of sins. "
    "We look for the resurrection of the dead, \n"
    "and the life of the world to come.\n"
    "\n"
    "Amen."
)

APOSTLES_CREED = (
    "I believe in God, the Father almighty,\n"
    "creator of heaven and earth.\n"
    "\n"
    f"I believe in Jesus Christ, God{APOSTROPHE}s only Son, our Lord,\n"
    "who was conceived by the Holy Spirit,\n"
    "born of the virgin Mary,\n"
    "suffered under Pontius Pilate,\n"
    "was crucified, died, and was buried;\n"
    "he descended to the dead.\n"
    "On the third day he rose again;\n"
    "he ascended into heaven,\n"
    "he is seated at the right hand of the Father,\n"
    "and he will come to judge the living and the dead.\n"
    "\n"
    "I believe in the Holy Spirit,\n"
    "the holy catholic church,\n"
    "the communion of saints,\n"
    "the forgiveness of sins,\n"
    "the resurrection of the body,\n"
    "and the life everlasting.\n"
    "\n"
    "Amen."
)

LORDS_PRAYER = (
    "Our Father, \n"
    "who art in heaven,\n"
    "hallowed be thy name,\n"
    "thy kingdom come,\n"
    "thy will be done,\n"
    "on earth as it is in heaven.\n"
    "\n"
    "Give us this day \n"
    "our daily bread;\n"
    "\n"
    "and forgive us \n"
    "our trespasses,\n"
    "\n"
    "as we forgive those \n"
    "who trespass against us;\n"
    "\n"
    "and lead us not into temptation,\n"
    "but deliver us from evil.\n"
    "\n"
    "For thine is the kingdom,\n"
    "and the power, \n"
    "and the glory,\n"
    "forever and ever.  Amen."
)

PRAYERS_INTRO = "We continue with the prayers of the people:"

DEFAULT_PRAYERS_RESPONSE = "Your mercy is great."

# ── Large Print liturgical texts (from LP reference DOCX) ──────────

# Great Thanksgiving — spoken P:/C: dialog (not notation in Large Print)
GREAT_THANKSGIVING_DIALOG = [
    (DialogRole.PASTOR, "The Lord be with you."),
    (DialogRole.CONGREGATION, "And also with you."),
    (DialogRole.PASTOR, "Lift up your hearts."),
    (DialogRole.CONGREGATION, "We lift them to the Lord."),
    (DialogRole.PASTOR, "Let us give thanks to the Lord our God."),
    (DialogRole.CONGREGATION, "It is right to give our thanks and praise."),
]

GREAT_THANKSGIVING_PREFACE = (
    "It is indeed right, our duty and our joy, that we should, "
    "at all times and in all places, give thanks and praise to you, "
    "almighty and merciful God, through our Savior Jesus Christ."
)

# Sanctus — bold congregation text (from LP reference para 167-171)
# Each stanza is a separate paragraph in the reference; double newline = para break.
SANCTUS = (
    "Holy, holy, holy Lord,\n"
    "God of power and might,\n"
    "\n"
    "Heaven and earth \n"
    "are full of your glory.\n"
    "\n"
    "Hosanna in the highest.\n"
    "\n"
    "Blessed is he who comes \n"
    "in the name of the Lord.\n"
    "\n"
    "Hosanna in the highest. Hosanna in the highest."
)

# Eucharistic Prayer — Extended form (Lent/Christmas/Epiphany)
EUCHARISTIC_PRAYER_EXTENDED = (
    "Blessed are you, O God of the universe.\n"
    "Your mercy is everlasting and your faithfulness endures from age to age.\n"
    "\n"
    "Praise to you for creating the heavens and the earth.\n"
    "Praise to you for saving the earth from the waters of the flood.\n"
    "Praise to you for bringing the Israelites safely through the sea.\n"
    "Praise to you for leading your people through the wilderness "
    "to the land of milk and honey.\n"
    "Praise to you for the words and deeds of Jesus, your anointed one.\n"
    "Praise to you for the death and resurrection of Christ.\n"
    "Praise to you for your Spirit poured out on all nations."
)

WORDS_OF_INSTITUTION = (
    "In the night in which he was betrayed, our Lord Jesus took bread, "
    "and gave thanks; broke it, and gave it to his disciples, saying:\n"
    "\n"
    "Take and eat; this is my body,\n"
    "given for you. Do this for the remembrance of me.\n"
    "\n"
    "Again, after supper, he took the cup, gave thanks, and gave it "
    "for all to drink, saying:\n"
    "\n"
    "This cup is the new covenant in my blood, shed for you and for all people "
    "for the forgiveness of sin.\n"
    "Do this for the remembrance of me."
)

MEMORIAL_ACCLAMATION = (
    "Christ has died.\n"
    "Christ is risen.\n"
    "Christ will come again."
)

EUCHARISTIC_PRAYER_CLOSING = (
    "O God of resurrection and new life:\n"
    "Pour out your Holy Spirit on us\n"
    "and on these gifts of bread and wine.\n"
    "\n"
    "Reveal yourself to us\n"
    "in the breaking of the bread.\n"
    "\n"
    "Raise us up as the body of Christ for the world. "
    "Breathe new life into us. Send us forth,\n"
    "burning with justice, peace, and love.\n"
    "\n"
    "With your holy ones of all times and places, "
    "with the earth and all its creatures, "
    "with sun and moon and stars, "
    "we praise you, O God, blessed and holy Trinity, "
    "now and forever."
)

COME_HOLY_SPIRIT = "Come, Holy Spirit."

# Agnus Dei — bold congregation text (from LP reference para 209-211)
AGNUS_DEI = (
    "Lamb of God, you take away the sin of the world;\n"
    "have mercy on us.\n"
    "Lamb of God, you take away the sin of the world;\n"
    "have mercy on us.\n"
    "Lamb of God, you take away the sin of the world;\n"
    "grant us peace."
)

# Nunc Dimittis — bold congregation text (from LP reference para 230-239)
NUNC_DIMITTIS = (
    "Now, Lord, you let your servant go in peace:\n"
    "your word has been fulfilled.\n"
    "My own eyes have seen the salvation\n"
    f"which you have prepared in the sight of ev{APOSTROPHE}ry people:\n"
    "a light to reveal you to the nations\n"
    "and the glory of your people Israel.\n"
    "Glory to the Father, and to the Son,\n"
    "and to the Holy Spirit,\n"
    "as it was in the beginning, is now,\n"
    "and will be forever. Amen."
)

# Aaronic Blessing (from LP reference para 243-245)
AARONIC_BLESSING = (
    "The Lord bless you and keep you.\n"
    f"The Lord{APOSTROPHE}s face shine on you with grace and mercy.\n"
    f"The Lord look upon you with favor and {CROSS} give you peace."
)

# Offertory Hymn — "Oh, come, Lord Jesus" (always the same)
OFFERTORY_HYMN_VERSES = [
    (
        "1\tOh, come, Lord Jesus,\n"
        "\tbe our guest,\n"
        "\tand let your gifts to us \n"
        "\tbe blest.\n"
        "  Keep us forever in your care,\n"
        "\tand save us from \n"
        "\tall harm and sorrow. \n"
        "\tAmen."
    ),
    (
        "2\tOh, come, Lord Jesus, \n"
        "\tbe our guest,\n"
        "\tand let your gifts to us \n"
        "\tbe blest.\n"
        "  Oh, may there be \n"
        "\ta goodly share \n"
        "\ton every table, everywhere.\n"
        "\tAmen."
    ),
]

# Welcome message (from LP reference)
WELCOME_MESSAGE = (
    "Welcome to Ascension. We are glad that you have chosen to worship with us today! "
    "May the Holy Spirit bless us as we worship and praise God together."
)

STANDING_INSTRUCTIONS = (
    f"{LQUOTE} * {RQUOTE}{NBSP}Indicates when the congregation stands. \n"
    "Bold lettering indicates the congregation reads aloud in UNISON."
)

# Church info for cover
CHURCH_NAME = "Ascension Lutheran Church"
CHURCH_ADDRESS = f"6481 Old Canton Road Jackson {MIDDOT} Mississippi {MIDDOT} 39211\n601.956.4263\nwww.ascensionlutheran.com"

# ── Standard ELW Confession and Forgiveness (Form A) ──────────────
# Used consistently at Ascension regardless of season.
# Structure: list of (DialogRole, text) tuples.
CONFESSION_AND_FORGIVENESS = [
    (DialogRole.INSTRUCTION,
     f"All may make the sign of the cross {CROSS}, "
     "the sign marked at our baptism, as Pastor begins."),
    (DialogRole.PASTOR,
     f"In the name of the Father, and of the {CROSS} Son, "
     "and of the Holy Spirit. Amen."),
    (DialogRole.NONE,
     "God of all mercy and consolation, come to the help of your people, "
     "turning us away from our sin to live for you alone. "
     "Give us the power of your Holy Spirit that we may confess our sin, "
     "receive your forgiveness, and grow into the fullness "
     "of Jesus Christ, our Savior and Lord. Amen."),
    (DialogRole.PASTOR, "Most merciful God,"),
    (DialogRole.CONGREGATION,
     "we confess that we are captive to sin and cannot free ourselves. "
     "We have sinned against you in thought, word, and deed, "
     "by what we have done and by what we have left undone. "
     "We have not loved you with our whole heart; "
     "we have not loved our neighbors as ourselves. "
     "For the sake of your son, Jesus Christ, have mercy on us. "
     "Forgive us, renew us, and lead us, "
     "so that we may delight in your will "
     "and walk in your ways, "
     "to the glory of your holy name. Amen."),
    (DialogRole.PASTOR,
     "In the mercy of almighty God, Jesus Christ was given to die for us, "
     "and for his sake God forgives us all our sins. "
     "As a called and ordained minister of the church of Christ, "
     "and by his authority, I therefore declare to you "
     "the entire forgiveness of all your sins, "
     f"in the name of the Father, and of the {CROSS} Son, "
     "and of the Holy Spirit. Amen."),
]


# Standard dismissal (Ascension always uses this, not S&S seasonal variant)
DISMISSAL = (
    "Go in peace to love and serve the Lord.\n"
    "Thanks be to God."
)

# Structured dismissal for call-and-response rendering.
# Same format as CONFESSION_AND_FORGIVENESS: (DialogRole, text).
DISMISSAL_ENTRIES = [
    (DialogRole.PASTOR, "Go in peace to love and serve the Lord."),
    (DialogRole.CONGREGATION, "Thanks be to God."),
]

# Invitation to Lent (same every year — not provided by S&S)
INVITATION_TO_LENT = (
    "Friends in Christ, today with the whole church we enter the time "
    f"of remembering Jesus{APOSTROPHE} passover from death to life, and our life "
    "in Christ is renewed.\n"
    "\n"
    "We begin this holy season by acknowledging our need for repentance "
    f"and for God{APOSTROPHE}s mercy. We are created to experience joy in communion "
    "with God, to love one another, and to live in harmony with creation. "
    "But our sinful rebellion separates us from God, our neighbors, and "
    "creation, so that we do not enjoy the life our creator intended.\n"
    "\n"
    "As disciples of Jesus, we are called to a discipline that struggles "
    "against evil and resists whatever leads us away from love of God and "
    f"neighbor. I invite you, therefore, to the discipline of Lent{EMDASH}"
    "self-examination and repentance, prayer and fasting, sacrificial giving "
    f"and works of love{EMDASH}strengthened by the gifts of word and sacrament.\n"
    "\n"
    "Let us continue our journey through these forty days to the great "
    f"Three Days of Jesus{APOSTROPHE} death and resurrection."
)


# ── Holy Baptism (abbreviated Sunday rite, ELW pp. 227-231) ──────

BAPTISM_PRESENTATION = (
    "God, who is rich in mercy and love, gives us a new birth into "
    "a living hope through the sacrament of baptism. By water and "
    "the Word, God delivers us from sin and death and raises us to "
    "new life in Jesus Christ."
)

BAPTISM_FLOOD_PRAYER = (
    "We give you thanks, O God, for in the beginning your Spirit moved "
    "over the waters and by your Word you created the world, calling "
    "forth life in which you took delight. Through the waters of the "
    "flood you delivered Noah and his family, and through the sea you "
    "led your people Israel from slavery into freedom. At the river "
    "your Son was baptized by John and anointed with the Holy Spirit. "
    "By the baptism of Jesus{APOSTROPHE} death and resurrection you set us "
    "free from the power of sin and death and raise us up to live in you."
).format(APOSTROPHE=APOSTROPHE)

BAPTISM_RENUNCIATION = [
    (DialogRole.PASTOR,
     "Do you renounce the devil and all the forces that defy God?"),
    (DialogRole.CONGREGATION, "I renounce them."),
    (DialogRole.PASTOR,
     "Do you renounce the powers of this world that rebel against God?"),
    (DialogRole.CONGREGATION, "I renounce them."),
    (DialogRole.PASTOR,
     "Do you renounce the ways of sin that draw you from God?"),
    (DialogRole.CONGREGATION, "I renounce them."),
]

BAPTISM_PROFESSION = [
    (DialogRole.PASTOR,
     "Do you believe in God the Father?"),
    (DialogRole.CONGREGATION,
     "I believe in God, the Father almighty, "
     "creator of heaven and earth."),
    (DialogRole.PASTOR,
     f"Do you believe in Jesus Christ, the Son of God?"),
    (DialogRole.CONGREGATION,
     f"I believe in Jesus Christ, God{APOSTROPHE}s only Son, our Lord, "
     "who was conceived by the Holy Spirit, "
     "born of the virgin Mary, "
     "suffered under Pontius Pilate, "
     "was crucified, died, and was buried; "
     "he descended to the dead. "
     "On the third day he rose again; "
     "he ascended into heaven, "
     "he is seated at the right hand of the Father, "
     "and he will come to judge the living and the dead."),
    (DialogRole.PASTOR,
     "Do you believe in God the Holy Spirit?"),
    (DialogRole.CONGREGATION,
     "I believe in the Holy Spirit, "
     "the holy catholic church, "
     "the communion of saints, "
     "the forgiveness of sins, "
     "the resurrection of the body, "
     "and the life everlasting."),
]

BAPTISM_FORMULA = (
    "{name}, I baptize you in the name of the Father, "
    f"and of the {CROSS} Son, and of the Holy Spirit. Amen."
)

BAPTISM_WELCOME = (
    "Let us welcome the newly baptized."
)

BAPTISM_WELCOME_RESPONSE = (
    "We welcome you into the body of Christ and into the mission "
    "we share: join us in giving thanks and praise to God "
    "and bearing God{APOSTROPHE}s creative and redeeming word to all the world."
).format(APOSTROPHE=APOSTROPHE)
