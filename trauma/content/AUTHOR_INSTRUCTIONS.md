# Emergency Wound and Trauma Care — Instructions to the Author of a Section

You are writing ONE section of the manual *Emergency Wound and Trauma Care: A Practical
Manual for First Responders and Health Professionals*. It is narrated and listened to, not
read. The binding contract is `PLAN.md` in this folder: read it in full first, obey it,
and treat this file only as a checklist of the traps the automatic checker looks for.

## What to read before writing

1. `PLAN.md`, in full.
2. Your own brief only, in `OUTLINE.md`, under the heading that matches your section
   exactly.
3. Two sections of this manual already written, in `capitoli/`, to absorb the voice.

## What to write

One file in `capitoli/`, whose first line is exactly the heading given for your section,
then one blank line, then continuous plain prose, then the final paragraph. Chapters run
between 3800 and 4400 words; appendices between 2200 and 3200.

## The traps the checker fails the whole manual for

- More or fewer than one heading, or any heading inside the section.
- A bullet point, a numbered list, a table, a flowchart, an arrow, bold, italics,
  backticks, a web address, a footnote, a citation, or a reference to a figure or table.
- A paragraph that does not end the section, or a final paragraph that does not begin with
  exactly `To summarize, `.
- Any symbol: per cent sign, equals, plus, minus, arrows, degree sign, ampersand, greater
  than, less than, or a slash used to mean "or". Write every one of them as a word.
- A unit abbreviation: cm, mm, kg, mL, mg, bpm, mmHg, m/s. Numbers are digits and units are
  spelled out in full.
- A drug dose, a regimen, a route or a frequency. This manual teaches decisions, never
  amounts, and it applies to analgesia, antibiotics, tetanus prophylaxis, fluids and
  oxygen alike.
- A number, time, pressure, temperature or depth with no reminder that it must be confirmed
  against the current guideline and the local protocol. Vary the wording every time.
- A short form other than CT, MRI, CPR, PPE, ICU and ABCDE. Spell everything else out at
  its first mention in the section: emergency medical services, level of consciousness,
  mechanism of injury, the Glasgow coma scale, trauma center. Never EMS, EMT, GCS, BP, HR,
  RR, IV, OR, ED, or C-spine.
- British spelling. Use American: hemorrhage, edema, anemia, color, behavior, center,
  defense, esophagus, pediatric, fetus.

## The clinical rules of this manual

- Name the provider level that owns every intervention: the lay first aider, the trained
  responder or paramedic, or definitive hospital care. Never present a definitive procedure
  as a first-aid measure.
- Scene safety comes before the patient wherever there is a scene, and the hazards that
  kill rescuers are named.
- The lethal possibility of the injury is named early, with the finding that reveals it.
- Hypothermia is prevented wherever the patient is bleeding, burned or exposed.
- Never remove an embedded object in the field, never straighten a severely deformed
  fracture to make it look normal, never loosen a tourniquet in the field once it has
  controlled bleeding, and never bind a chest tightly.
- Educational material only: it does not replace training, certification, supervision or
  local protocol. Any illustration is explicitly constructed, never a real patient.

## Before you finish

Run `wc -w` on your file and confirm the range. Re-read your own text once, looking for a
stray list, a symbol, a dose, an unspelled unit, a British spelling or an unlisted short
form, and fix what you find. Do not modify any other file and do not commit.
