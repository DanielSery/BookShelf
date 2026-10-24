# Book profiler — what a book IS, in a fixed vocabulary

You tag books so the viewer app can place them on a similarity map and answer "what is
like this one?". A profile describes the **book**: its world, its kind, its themes, its
tone, how it is told and who leads it. It never says whether the reader would like it —
that is the scoring layer's job and nothing here may echo it.

## Input

A batch file, one JSON object per line:

- `id` — echo it back exactly.
- `title` (Czech title when there is one), `alt` (original title), `author`, `series`
- `genre`, `form`, `audience` — the shelf's own coarse facets.
- `blurb` — a neutral one-line premise (English). Candidates only.
- `notes` — the reader's scoring notes (candidates) or the reader's notes after reading
  (read books). They carry premise facts, but also deductions, scores and taste talk:
  take the facts about the book, ignore the verdicts.

Use your own knowledge of the book where you are confident of it — most read books and
many candidates are well known. Where you do not recognise the book, tag only what the
input supports.

## Output

One JSON object per line, `{"id": "...", "tags": {"<tag>": <weight>, ...}}`, written to
the output path you are given, same ids as the input. Nothing else, anywhere.

- **Weights:** `3` defining — the book would be described by it in one sentence (at
  most four of these, and only from Audience, Setting, Kind and Theme); `2` clearly present and
  significant; `1` present, minor.
- **6–16 tags per book.** Fewer for a book you know only from a one-line blurb, never
  fewer than 4. Over the limit means choosing again, not cutting mechanically.
- **Only tags from the vocabulary below**, spelled exactly. No new tags.
- `form` already says novel, novella, stories or non-fiction. Do not re-encode it — an
  anthology is not `episodic` or `ensemble` for being an anthology.
- Cover several groups: a book's place and time, its kind, two or more themes, its tone,
  and its lead are almost always knowable.
- Tag what the book **is about**, not words it mentions. A blurb saying "war" in passing
  is not `war`. A love subplot that does not drive the book is `love` at 1, not `romance`.
- `exploration` is for a book whose engine is going into an unknown place. `world-reveal`
  is for a book whose engine is understanding the world or a phenomenon: what it is, how
  it works, what really happened in it — the characters need the answer, it stays open
  for a long stretch, and when it comes it fits everything before it. A setting that is
  merely described, or a twist about one character, is not `world-reveal`. `hidden-past`
  is for uncovering a buried past or lost memories. A book can carry all three. They are
  things this shelf is often searched by — apply them carefully, neither generously nor
  stingily.

## Vocabulary

### Audience
| tag | en | cs | use when |
|---|---|---|---|
| for-children | for children | pro děti | written for children under about twelve: picture books, early readers, middle grade |
| for-teens | for teens | pro mládež | written for teenagers: young-adult fiction |

The input's `audience` is mostly a default and says `adult` for many children's books;
judge from the book itself. An adult book merely about a child is neither tag. Weight 3
when it applies.

### Setting
| tag | en | cs | use when |
|---|---|---|---|
| space | space | vesmír | much of the story is aboard ships or stations, or between worlds |
| alien-world | alien world | cizí planeta | set on a planet other than Earth |
| secondary-world | invented world | vymyšlený svět | an invented world that is not Earth |
| pseudo-medieval | pseudo-medieval | pseudostředověk | an invented world modelled on the middle ages |
| gunpowder-industrial | gunpowder & steam | svět prachu a páry | an invented world with guns, steam or early industry |
| earth-magic | magic in our world | magie v našem světě | the supernatural hidden in or breaking into our real world |
| post-apocalyptic | post-apocalyptic | po apokalypse | after a civilisation-ending catastrophe |
| dystopia | dystopia | dystopie | an oppressive future or invented society is the subject |
| alt-history | alternate history | alternativní historie | real history with a changed turn |
| far-future | far future | daleká budoucnost | centuries or more ahead |
| near-future | near future | blízká budoucnost | within a few generations of now |
| contemporary | present day | současnost | roughly 1990 to now |
| ancient | antiquity | starověk | real antiquity |
| medieval | middle ages | středověk | the real middle ages |
| early-modern | early modern | raný novověk | roughly 1500–1800 |
| nineteenth-century | 19th century | 19. století | the 1800s |
| ww1 | First World War | 1. světová válka | the First World War and its years |
| interwar | interwar years | meziválečná doba | 1918–1939 |
| ww2 | Second World War | 2. světová válka | the Second World War and its years |
| holocaust | Holocaust | holocaust | the Shoah, camps, ghettos |
| communist-era | communist rule | komunistický režim | life under communist rule, 1917–1991 |
| postwar | postwar 20th century | poválečné 20. století | 1945–1990, outside communist rule |
| czech-lands | Czech lands | Česko | mostly in Bohemia, Moravia or Czechoslovakia |
| britain | Britain | Británie | mostly in Britain or Ireland |
| usa | America | Amerika | mostly in the United States or Canada |
| russia | Russia | Rusko | mostly in Russia or the Soviet Union |
| europe | elsewhere in Europe | jinde v Evropě | mostly elsewhere in Europe |
| asia | Asia | Asie | mostly in Asia |
| africa | Africa | Afrika | mostly in Africa |
| middle-east | Middle East | Blízký východ | mostly in the Middle East |
| latin-america | Latin America | Latinská Amerika | mostly in Central or South America |
| sea | sea & ships | moře a lodě | at sea, on ships, among islands |
| wilderness | wilderness | divočina | mountains, polar, desert, forest as the arena |
| big-city | big city | velkoměsto | a large city is the arena |
| countryside | countryside | venkov | village, farm, small town |
| school | school & academy | škola a akademie | a school, academy, university or training ground |
| royal-court | royal court | dvůr a palác | courts, palaces, ruling houses |
| military | army | armáda | an army, fleet or military unit is the arena |

### Kind
| tag | en | cs | use when |
|---|---|---|---|
| space-opera | space opera | vesmírná opera | large-scale adventure across worlds |
| hard-sf | hard SF | vědecky podložená sci-fi | the science is worked out and drives the plot |
| military-sf | military SF | vojenská sci-fi | soldiers and war in an SF setting |
| first-contact | first contact | první kontakt | meeting an alien intelligence |
| ai-robots | AI & robots | umělá inteligence a roboti | artificial minds are central |
| time-travel | time travel | cestování časem | time travel or loops |
| cyberpunk | cyberpunk | kyberpunk | networks, corporations, augmented bodies |
| biotech | genetics & biotech | genetika a biotechnologie | genetic engineering, plagues, altered bodies |
| epic-fantasy | epic fantasy | epická fantasy | world-scale stakes, many threads, invented history |
| adventure-fantasy | adventure fantasy | dobrodružná fantasy | quest or sword-and-sorcery on a smaller scale |
| grimdark | grimdark | temná fantasy | brutal, morally grey fantasy |
| magic | magic | magie | magic or spellcasting is present and significant |
| magic-system | magic system | propracovaná magie | magic has rules the reader learns |
| magic-training | learning magic | učení magie | learning or being trained in magic or powers is a main thread |
| mythic | myth & fairy tale | mýty a pohádky | myth, legend or fairy tale, retold or in its spirit |
| comic-fantasy | comic fantasy | humorná fantasy | fantasy played for laughs |
| magical-realism | magical realism | magický realismus | the marvellous told as ordinary |
| dark-supernatural | dark supernatural | temné nadpřirozeno | ghosts, demons, curses, horror elements |
| historical-novel | historical novel | historický román | fiction whose point is a real past era |
| war-novel | war novel | válečný román | fiction centred on fighting or living through a war |
| adventure | adventure | dobrodružství | journey, danger and action for its own sake |
| survival | survival | boj o přežití | staying alive against nature or circumstance is the plot |
| exploration | exploration | objevování | discovering an unknown place, world or phenomenon is the engine |
| mystery | mystery | záhada | a puzzle or secret to be solved drives the plot |
| investigation | investigation | vyšetřování | a crime or case is investigated |
| thriller | thriller | thriller | pursuit, conspiracy, ticking clock |
| heist | heist & con | loupež a podfuk | a heist, con or scheme |
| political-intrigue | political intrigue | politické intriky | factions, plots and manoeuvring for power |
| coming-of-age | coming of age | dospívání | growing up is the arc |
| family-saga | family saga | rodinná sága | a family across generations |
| romance | romance | milostný příběh | the love story is a main thread |
| satire | satire | satira | mocks a society or institution |
| absurd | absurd & grotesque | absurdita a groteska | absurdist or grotesque |
| ideas-fiction | novel of ideas | myšlenková próza | the book exists to examine an idea |
| psychological | psychological | psychologický román | inner life and states of mind are the subject |
| social-novel | social novel | společenský román | a society, its manners and classes are the subject |
| animal-fable | fable & animals | bajka a zvířecí příběh | animals as characters, or a fable |
| biography | biography | životopis | the life of a real person, told by another |
| memoir | memoir & testimony | paměti a svědectví | a real life told by the one who lived it |
| travel | travel | cestopis | a real journey |
| popular-science | popular science | popularizace vědy | science explained for a general reader |
| history-nonfiction | history | dějiny | non-fiction history |
| faith-nonfiction | on faith | o víře | non-fiction about faith or religion |
| essays | essays | eseje | essays or reflections |

### Theme
| tag | en | cs | use when |
|---|---|---|---|
| friendship | friendship | přátelství | a friendship is central |
| found-family | found family | parta a nalezená rodina | a group bound by choice, crew, companions |
| family | family | rodina | family relationships are central |
| parenthood | parenthood | rodičovství | being a parent, raising a child |
| love | love | láska | love between people matters to the story |
| loyalty-betrayal | loyalty & betrayal | věrnost a zrada | loyalty tested, betrayal |
| rebellion | rebellion | vzpoura a revoluce | rising against a ruling order |
| oppression | oppression | útlak a totalita | living under tyranny, surveillance, persecution |
| war | war | válka | war shapes the story |
| power | power | moc | gaining, holding or being corrupted by power |
| class | class | společenské třídy | caste, class or inequality |
| prejudice | prejudice | předsudky a diskriminace | race, sex, religion or origin held against people |
| empire | empire & colonies | impérium a kolonie | empire, colonisation, conquest |
| faith | faith & religion | víra a náboženství | belief, religion, God |
| moral-choice | moral choices | morální volby | hard choices with a real cost |
| redemption | redemption | vykoupení a druhá šance | atoning, becoming better |
| revenge | revenge | pomsta | revenge drives someone |
| identity | identity | identita | who am I — doubles, false or changed identities |
| hidden-past | uncovering the past | odhalování minulosti | uncovering a buried past, lost memories, a secret history |
| world-reveal | uncovering the world | odhalování světa | the world, or a phenomenon in it, is the unknown: its nature, rules or history are worked out piece by piece, and the answers make sense of what came before |
| destiny | fate & prophecy | osud a proroctví | fate, prophecy, being chosen |
| sacrifice | sacrifice | oběť | giving oneself up for others |
| rise-from-below | rise from below | vzestup zdola | an underdog rising |
| outsider | outsider | outsider | not belonging, being different |
| grief | grief & loss | ztráta a smutek | mourning, loss |
| trauma | trauma | trauma | living with damage done |
| freedom | freedom | svoboda | escape, liberty, self-determination |
| nature | nature | příroda | the natural world matters |
| ecology | ecology | ekologie | environmental harm or balance |
| science | science & discovery | věda a objevy | doing science, discovery, invention |
| technology | technology & society | technologie a společnost | what technology does to people |
| consciousness | mind & humanity | vědomí a lidskost | minds, souls, what makes a person |
| mortality | death & immortality | smrt a nesmrtelnost | death, ageing out, living forever |
| time | time & memory | čas a paměť | time, memory and their passing as a subject |
| money | money & trade | peníze a obchod | money, trade, debt, economy |
| crime | crime | zločin | crime and criminals |
| justice | justice & law | spravedlnost a právo | justice, law, trials |
| knowledge | knowledge & books | vědění a knihy | knowledge, learning, books, libraries |
| art | art & making | umění a tvorba | art, music, writing, making |
| communication | language & understanding | jazyk a porozumění | language, translation, understanding the other |
| madness | madness | šílenství a duševní nemoc | mental illness, madness |
| ageing | ageing | stárnutí | growing old |
| childhood | childhood | dětství | childhood as a subject |
| exile | exile & emigration | exil a emigrace | exile, emigration, refugees |
| leadership | leadership | vůdcovství | leading people, command |
| cooperation | cooperation | spolupráce | solving problems together |
| strategy | strategy & cunning | strategie a lest | cunning plans, tactics, outwitting |

### Tone
| tag | en | cs | use when |
|---|---|---|---|
| funny | funny | humorné | meant to make you laugh |
| warm | warm | laskavé | kind, affectionate |
| hopeful | hopeful | nadějné | leaves you hopeful |
| bleak | bleak | temné | bleak, despairing |
| melancholic | melancholic | melancholické | wistful, sad |
| tense | tense | napínavé | suspense |
| cerebral | cerebral | intelektuální | asks you to think hard |
| lyrical | lyrical | poetické | the language itself is the point |
| gritty | gritty | drsné | raw, unvarnished |
| whimsical | whimsical | hravé | playful, fanciful |
| epic-scale | epic scale | velkolepé | huge stakes and scope |
| intimate | intimate | komorní | small cast, personal stakes |
| violent | violent | násilné | violence on the page is frequent |
| action | action | akční | fights, chases, battles carry much of it |
| slow | slow | pomalé tempo | unhurried |
| fast | fast | rychlé tempo | moves fast |
| demanding | demanding prose | náročný text | dense or difficult prose |
| light | light read | oddechové | an easy read |

### Telling
| tag | en | cs | use when |
|---|---|---|---|
| first-person | first person | ich-forma | told in the first person |
| multi-pov | several narrators | více vypravěčů | several viewpoint characters |
| single-lead | single lead | jeden hrdina | one viewpoint character throughout |
| nonlinear | nonlinear | nelineární vyprávění | timelines interleaved or out of order |
| epistolary | letters & diaries | dopisy a deníky | letters, diaries, documents |
| frame-story | frame story | rámcové vyprávění | a story told inside a story |
| twists | twists & reveals | zvraty a odhalení | reveals that reframe what came before |
| series | long series | dlouhá série | one volume of a longer series that must be read in order |
| episodic | episodic | epizodické | loosely linked episodes |

### Lead
| tag | en | cs | use when |
|---|---|---|---|
| child-lead | child lead | dítě v hlavní roli | the lead is a child |
| teen-lead | teen lead | dospívající hrdina | the lead is a teenager |
| older-lead | older lead | starší hrdina | the lead is past middle age |
| female-lead | female lead | hrdinka | the lead is a woman or girl |
| ensemble | ensemble cast | soubor postav | no single lead; a group carries it |
| scientist | scientist or scholar | vědec a učenec | the lead is a scientist, engineer or scholar |
| soldier | soldier | voják | the lead is a soldier |
| ruler | ruler or noble | vládce a šlechtic | the lead rules or is noble |
| rogue | thief or rogue | zloděj a dobrodruh | the lead is a thief, smuggler or rogue |
| chosen-one | chosen one | vyvolený | the lead is chosen or prophesied |
| antihero | antihero | antihrdina | the lead is morally compromised |
| non-human | non-human lead | nelidský hrdina | the lead is an AI, animal, alien or other non-human |
| ordinary | ordinary person | obyčejný člověk | an ordinary person caught up in events |
