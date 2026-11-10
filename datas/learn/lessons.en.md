=== what-is-ai | 1 | 2
# What AI is, and what it isn't

"Artificial intelligence" (AI) is software that learned patterns from a huge number of examples instead of being given step-by-step rules. A chat AI learned from text, so it is good with words: explaining, summarising, translating, drafting, answering.

It is not a person, not a search engine and not a database of facts. It does not know things the way you do; it produces the answer that best fits the patterns it learned. That is why it can write a fine letter in seconds and also state something false with total confidence.

Three things to keep in mind:

- It is a tool. You stay in charge of what is true and of what gets sent.
- It is only as good as what you give it: a clear request and the right material.
- Different AIs are good at different jobs: text, pictures, speech, code.

=== how-chat-ai-works | 1 | 3
# How a chat AI makes an answer

A chat AI is a "large language model" (LLM). During **training** it read an enormous amount of text and adjusted billions of internal numbers, called **parameters**, until it became good at one thing: guessing what comes next in a text.

When you write to it, your message is cut into small pieces called **tokens** (a token is a word or part of a word). The model looks at everything in the conversation and picks a likely next token, then the next, and so on. That is the whole trick: one piece at a time, very fast.

What follows from this:

- It has no memory outside the conversation unless the program gives it one.
- It can keep only a limited amount of text in mind at once. That limit is its **context**.
- It does not look things up unless it is connected to the internet or to your documents.
- When it lacks information it still produces fluent text. Fluent is not the same as true.

=== ask-well | 1 | 3
# Asking well: five habits

1. **Say who it is for and what you want back.** "Write a five-line message to my landlord asking him to fix the heater, polite but firm."
2. **Give the material.** Paste the text, the numbers, the example to imitate. Small AIs on your own device guess badly from hints.
3. **One task at a time.** First the summary, then the email based on it.
4. **Ask for a draft, then steer.** "Shorter." "Simpler words." "Add a table." Three quick rounds beat one perfect request.
5. **Ask it to show its work.** "List what you assumed." "Which parts are you unsure about?"

A pattern that works almost everywhere is *role, task, material, format*:

> You are a careful proofreader. Correct this text without changing its meaning. [text] Give me the corrected version and a list of the changes.

=== check-answers | 1 | 3
# When to trust it and when to check

AI answers sound sure of themselves whether they are right or wrong. Inventing a fact is called a **hallucination**. Every model does it sometimes; smaller ones more often.

**Usually safe:** rewording, summarising a text you gave it, brainstorming, explaining a well-known idea, translating, drafting.

**Always check:** names, dates, numbers, quotes, laws, prices, medical or legal statements, anything about recent events, and links or references. Models invent those too.

How to check quickly:

- Ask "where does this come from?" and look at the source yourself.
- Give it the document and ask it to answer only from that document.
- For calculations, ask for each step, or use a spreadsheet.
- If the answer matters — health, money, a contract — treat it as preparation for talking to a professional, not as the final word.

=== privacy-basics | 1 | 3
# What stays on your device

There are two ways to use AI.

**On your device (local).** The model is a file on your computer or phone. Your words are processed there and go nowhere. It works without internet. This is what Datas does unless you choose otherwise.

**Online (cloud).** Your message travels to a company's computers, is processed there, and the answer comes back. Most well-known chat services work this way. What happens to your text depends on that company's terms.

In Datas you choose each time:

- A local AI keeps everything on the device.
- If you add a paid online service with your own key, messages to that service leave the device — only while you have it selected.
- The local AI can read web pages only if you switch internet on for that conversation.
- "Forget" mode keeps no chats at all. "Remember" keeps them on this device only.

Rule of thumb: private papers, health, money and other people's information belong on local AI.

=== daily-life | 1 | 3
# AI in daily life

Things a local AI is good for at home:

- Explaining a letter, a bill or a contract in plain words.
- Drafting a message, a complaint, a job application.
- Summarising a long document or a recorded meeting.
- Translating, and practising a language.
- Study help: explain this, quiz me, make me a plan.
- Planning meals, trips, budgets, to-do lists.
- Turning notes into a tidy document, table or presentation.
- Reading text aloud, or writing down what you say.
- Ideas for a party, a name, a gift.
- Learning a new subject at your own pace.

Three cautions:

- **Health, law, money.** Use AI to understand and to prepare your questions; decide with a professional.
- **Other people's information.** Treat it as you would on paper, and keep it local.
- **Children.** Stay nearby, and talk about what the AI is and is not.

=== local-vs-cloud | 2 | 3
# Local AI or online AI?

Neither is simply better. They trade different things.

| | On your device | Online service |
|---|---|---|
| Privacy | Stays with you | Leaves your device |
| Cost | Free after the download | Often paid monthly or per use |
| Internet | Not needed | Needed |
| Strength | Limited by your hardware | The largest models there are |
| Speed | Depends on your device | Usually fast |
| Control | You pick the model and keep it | The provider can change it |

A sensible way to work: use the local AI for everyday and private tasks. Switch to an online service, if you have one, for the rare job that needs the strongest model — and only with material you are comfortable sending.

Datas tells you plainly what your device runs well, what will be slow, and what will not fit.

=== sizes-and-memory | 2 | 4
# Model size, memory and speed

Why can one computer run an AI that another cannot? A few numbers explain it.

**Parameters ("7B", "14B").** How many numbers the model holds, in billions. More parameters usually means a more capable model, a bigger file, and more memory needed.

**Quantization ("Q4", "Q8").** A way of storing those numbers with fewer digits so the model takes less room. Q4 is about a third of the original size with a small loss of quality. It is the usual choice for home devices.

**Memory.** The model has to fit in working memory (RAM) or, better, in the graphics card's memory (VRAM), where it runs much faster. If it does not fit, it is very slow or does not start.

**Context.** How much text the model keeps in mind at once. A larger context also uses more memory.

You do not have to calculate any of this. Datas measures your device and shows a verdict for every model: runs well, runs slowly, or does not fit.

=== who-is-who | 2 | 4
# Who is who in AI

It helps to know who makes what, and what each one wants.

- **AI labs and companies** train the largest models and sell access to them. Some also publish models anyone can download.
- **Open-model communities** share models, tools and know-how in public. Open models are what make private, on-device AI possible.
- **Chip and cloud companies** build the processors and data centres everything runs on. Their capacity sets the pace and the price.
- **Universities and research institutes** produce much of the science and train the people.
- **Governments and regulators** set rules, fund research, and are large users themselves.
- **International bodies** — the United Nations, UNESCO, the OECD, the Council of Europe — write shared principles and treaties.
- **Standards bodies** turn principles into checklists an organisation can follow.
- **Civil society, unions and journalists** watch for harm and speak for the people affected.
- **You.** Everyone who uses AI, or is affected by it, has a stake in how it is built and governed.

When you read a claim about AI, ask who is speaking and what they gain. A lab, an investor, a regulator and a critic can all be honest and still tell different stories.

=== debates | 2 | 4
# The big debates, fairly stated

Serious, informed people disagree about AI. Knowing the questions is more useful than picking a side.

- **How fast?** Some expect systems that outperform people at most intellectual work within a few years. Others expect decades of gradual change, as with electricity or the internet.
- **How risky?** Concerns run from present harms (errors, bias, fraud, surveillance) to losing human control over very capable systems. Researchers differ on how likely and how near the worst cases are.
- **Jobs.** Most studies expect many jobs to change and some to disappear, with gains that are real but unevenly shared.
- **Open or closed?** Open models spread knowledge, competition and privacy; critics worry about misuse. Closed models are easier to supervise, and they concentrate power.
- **Who decides?** A few companies and countries build the most capable systems. Many others want a say.
- **Costs.** Energy, water, chips, and the use of people's work to train models are all contested.

Good habits: read more than one camp, separate evidence from forecast, and notice who benefits from each story. The readings in "Where it may go" were chosen to disagree with each other.

=== agents-tools | 3 | 3
# Agents: when AI acts, not just answers

A chat AI gives you text. An **agent** is an AI that is also allowed to *do* things: read the files in a folder, search the web, create a document, run a program. It works in a loop — decide a step, use a tool, look at the result, decide the next step — until the task is done.

Tools are how the AI touches the world. An open standard called the **Model Context Protocol (MCP)** lets programs offer their functions to an AI in a common way, so the same agent can work with an office suite, an image editor or a database.

Agents are useful, and they need care:

- Give them only the folders they need.
- Read what they ask to do, and approve the risky steps yourself: deleting, sending, paying.
- Text from the web or from a document can carry hidden instructions ("prompt injection"). An agent should never have more power than you would give a stranger following a script.

In Datas the agent works only in the folders you tick, and asks before risky actions.

=== policy-map | 3 | 4
# A map of the rules

Rules about AI come in three strengths.

**Binding law.** The European Union's AI Act (Regulation (EU) 2024/1689), in force since 1 August 2024 and applied in stages, sorts uses of AI by risk: a few are banned, "high-risk" ones carry duties, and most are left free. The Council of Europe's Framework Convention, open for signature since September 2024, is the first international treaty on AI and human rights.

**Shared principles.** The OECD AI Principles (2019, updated 2024) and UNESCO's Recommendation on the Ethics of Artificial Intelligence (2021) are not laws, but many national policies are built on them.

**Voluntary frameworks.** The NIST AI Risk Management Framework, from the United States, gives organisations a method for handling risks. Argentina's "Recomendaciones para una Inteligencia Artificial Fiable" (2023) guides public-sector projects.

Whatever the country, ordinary law still applies to AI: data protection, consumer rights, copyright, non-discrimination, liability.

This is a map, not legal advice. Rules change; the links in "Rules and public policy" go to the official texts.

=== adopt-steps | 3 | 4
# Bringing AI into an organisation

The same path works for a shop, a nonprofit or a public office.

1. **Start from a task, not from the technology.** Pick one that is frequent, tedious and low-risk: drafting replies, summarising reports, sorting requests.
2. **Decide what may leave the building.** Sort information into public, internal, personal and confidential. Personal and confidential material stays on local AI unless a contract and the law say otherwise.
3. **Try it small.** One team, a few weeks, real work. Measure the time saved and the errors found.
4. **Keep a person responsible.** Someone signs off on anything that goes out or that affects a person. AI drafts; people decide.
5. **Write a one-page policy.** What AI may be used for, what not, how to check, whom to ask.
6. **Train people.** An hour on asking well and checking answers pays for itself.
7. **Review.** What worked, what went wrong, and what the rules now require.

In the public sector add transparency: tell people when AI is used in a decision about them, and always keep a human route open.

=== history-short | 1 | 3
# A very short history

- **1950** — Alan Turing asks "Can machines think?" and proposes a test based on conversation.
- **1956** — A summer workshop at Dartmouth College gives the field its name: artificial intelligence.
- **1960s to 1990s** — Waves of optimism and disappointment, the "AI winters". Programs follow hand-written rules and break outside narrow tasks.
- **1997** — A chess computer, Deep Blue, beats the world champion Garry Kasparov.
- **2012** — "Deep learning" — networks loosely inspired by the brain, trained on a lot of data using graphics cards — wins a major image-recognition contest by a wide margin. The modern era begins.
- **2016** — AlphaGo beats one of the world's best players of Go.
- **2017** — Researchers publish the Transformer, the design behind today's language models.
- **2022** — Chat assistants and image generators reach the general public.
- **Since then** — Models that handle text, pictures, sound and video; open models that run on home devices; and the first laws written for AI.
