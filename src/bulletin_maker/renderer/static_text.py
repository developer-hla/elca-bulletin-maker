"""Fixed liturgical texts used in document generation.

Texts that S&S does NOT provide (confirmed via investigation):
Kyrie, Canticle of Praise, Great Thanksgiving dialog, Sanctus,
Agnus Dei, Nunc Dimittis, Lord's Prayer, Offertory Hymn.

S&S DOES provide: Confession, Prayer of Day, Readings, Gospel Acclamation,
Prayers, Offering Prayer, Invitation to Communion, Prayer After Communion,
Blessing, Dismissal.
"""

from __future__ import annotations

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
    "I believe in Jesus Christ, God\u2019s only Son, our Lord,\n"
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
    ("P", "The Lord be with you."),
    ("C", "And also with you."),
    ("P", "Lift up your hearts."),
    ("C", "We lift them to the Lord."),
    ("P", "Let us give thanks to the Lord our God."),
    ("C", "It is right to give our thanks and praise."),
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
    "which you have prepared in the sight of ev\u2019ry people:\n"
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
    "The Lord\u2019s face shine on you with grace and mercy.\n"
    "The Lord look upon you with favor and \u2629 give you peace."
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
    "\u201c * \u201d\u00a0Indicates when the congregation stands. \n"
    "Bold lettering indicates the congregation reads aloud in UNISON."
)

# Church info for cover
CHURCH_NAME = "Ascension Lutheran Church"
CHURCH_ADDRESS = "6481 Old Canton Road Jackson \u00b7 Mississippi \u00b7 39211\n601.956.4263\nwww.ascensionlutheran.com"

# ── Standard ELW Confession and Forgiveness (Form A) ──────────────
# Used consistently at Ascension regardless of season.
# Structure: list of (role, text, bold) tuples.
#   role: "Pastor" / "P" / "C" / "instruction" / ""
#   text: the paragraph text
#   bold: whether the text (not the label) should be bold
CONFESSION_AND_FORGIVENESS = [
    ("instruction",
     "All may make the sign of the cross \u2629, "
     "the sign marked at our baptism, as Pastor begins.",
     False),
    ("Pastor",
     "In the name of the Father, and of the \u2629 Son, "
     "and of the Holy Spirit. Amen.",
     False),
    ("",
     "God of all mercy and consolation, come to the help of your people, "
     "turning us away from our sin to live for you alone. "
     "Give us the power of your Holy Spirit that we may confess our sin, "
     "receive your forgiveness, and grow into the fullness "
     "of Jesus Christ, our Savior and Lord. Amen.",
     False),
    ("P", "Most merciful God,", False),
    ("C",
     "we confess that we are captive to sin and cannot free ourselves. "
     "We have sinned against you in thought, word, and deed, "
     "by what we have done and by what we have left undone. "
     "We have not loved you with our whole heart; "
     "we have not loved our neighbors as ourselves. "
     "For the sake of your son, Jesus Christ, have mercy on us. "
     "Forgive us, renew us, and lead us, "
     "so that we may delight in your will "
     "and walk in your ways, "
     "to the glory of your holy name. Amen.",
     True),
    ("P",
     "In the mercy of almighty God, Jesus Christ was given to die for us, "
     "and for his sake God forgives us all our sins. "
     "As a called and ordained minister of the church of Christ, "
     "and by his authority, I therefore declare to you "
     "the entire forgiveness of all your sins, "
     "in the name of the Father, and of the \u2629 Son, "
     "and of the Holy Spirit. Amen.",
     False),
]


# Standard dismissal (Ascension always uses this, not S&S seasonal variant)
DISMISSAL = (
    "Go in peace to love and serve the Lord.\n"
    "Thanks be to God."
)

# Invitation to Lent (same every year — not provided by S&S)
INVITATION_TO_LENT = (
    "Friends in Christ, today with the whole church we enter the time "
    "of remembering Jesus\u2019 passover from death to life, and our life "
    "in Christ is renewed.\n"
    "\n"
    "We begin this holy season by acknowledging our need for repentance "
    "and for God\u2019s mercy. We are created to experience joy in communion "
    "with God, to love one another, and to live in harmony with creation. "
    "But our sinful rebellion separates us from God, our neighbors, and "
    "creation, so that we do not enjoy the life our creator intended.\n"
    "\n"
    "As disciples of Jesus, we are called to a discipline that struggles "
    "against evil and resists whatever leads us away from love of God and "
    "neighbor. I invite you, therefore, to the discipline of Lent\u2014"
    "self-examination and repentance, prayer and fasting, sacrificial giving "
    "and works of love\u2014strengthened by the gifts of word and sacrament.\n"
    "\n"
    "Let us continue our journey through these forty days to the great "
    "Three Days of Jesus\u2019 death and resurrection."
)
