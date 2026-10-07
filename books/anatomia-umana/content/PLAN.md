# Human anatomy — narrated course in Italian

Editorial plan and style contract for the chapters intended for speech synthesis (MP3).

Goal: **≥ 1 MB of clean text** (≈ 168,000 words), divided into **55 chapters**
of ~3,000–3,400 words each, readable aloud without stumbling.

Reference backbone: structure and terminology of the *Anatomy of the Human Body*
(Henry Gray, 1918, public-domain edition): Osteology, Arthrology, Myology,
Angiology, Splanchnology, Neurology, Organs of the senses. The contents are **original
generated text**, not a copy or a translation of the work.

---

## 1. Style contract (binding)

The text is read by an Italian speech synthesizer. Everything that is not
pronounceable is a defect.

**File format**

- First line, and the only heading allowed: `# Capitolo N — Titolo del capitolo`
- No other title, no subtitle, no `##`.
- No bulleted or numbered list, no table, no code block.
- No note marker, no bibliographic reference, no URL, no
  cross-reference to figures ("come mostra la figura 3" is forbidden).
- Paragraphs separated by a blank line. Paragraphs of 4–8 sentences.
- Plain text only: no internal `*`, `**`, `_`, backticks, `|`, `#`, `>`.

**Prose**

- Discursive, continuous prose, in an erudite popular-scientific register: it really
  explains, it does not list.
- Sentences of medium length, well linked to one another. Avoid periods longer than 45 words.
- Every abstract concept must be anchored to a concrete image or a functional
  example (what happens, what it is for, what one observes).
- No strings of rhetorical questions, no "come tutti sappiamo".
- No filler adverbs and no formulaic repetitions across chapters.

**Numbers, abbreviations, symbols**

- Abbreviations always spelled out at first occurrence and then used in full form:
  "sistema nervoso centrale", not "SNC"; "adenosina trifosfato", not "ATP".
- Forbidden symbols: `%`, `=`, `+`, `→`, `<`, `>`, `&`, `°`. One writes "per cento",
  "uguale a", "più", "porta a", "gradi".
- Units of measurement written out in full: centimetri, millimetri, litri, millilitri,
  chilogrammi, grammi.
- Small numbers and cardinal numbers in words when they flow in the discourse
  ("due atri", "ventiquattro coste"); Roman numerals are spelled out ("nervo
  cranico settimo").
- Dates and centuries in words ("diciannovesimo secolo").

**Terminology**

- Standard Italian term as the main form (Terminologia Anatomica,
  Italian denomination). Latin is introduced in discursive form:
  "il muscolo sternocleidomastoideo, detto anche sternocleidomastoideus".
- Correct Italian spelling, correct accents and apostrophes, guillemets
  or straight double quotes, simple hyphens.

**Content**

- Anatomical precision: topographic relations, origin and insertion, vascularization
  and innervation where relevant, function, functional clinical correlates.
- Level: motivated student / cultured enthusiast. Technical vocabulary may be used
  but must be explained at first appearance.
- No medical advice, no diagnosis, no therapy: only descriptive anatomy and
  physiology.
- Each chapter closes with a summary paragraph that begins with
  "Riassumendo, " and is not introduced by any heading.

**Length**

- 3,000–3,400 words per chapter. Count the words before delivering.

---

## 2. Structure and index of the 55 chapters

### Part one — Introduction and organization of the body

1. What anatomy is: methods of study, reference planes, terms of position and movement
2. The fundamental tissues: epithelial, connective, muscular, nervous
3. The skeleton as a whole: functions of bone, types of bones, growth and remodeling
4. The muscular system as a whole: muscle fiber, contraction, levers and levers of the body

### Part two — Osteology and arthrology

5. The vertebral column: vertebrae, curves, discs and vertebral canal
6. The thoracic cage: ribs, sternum, costo-vertebral joints and mechanics of breathing
7. The neurocranium: bones of the vault and of the base
8. The splanchnocranium: bones of the face, orbit, nasal cavities and cranial fossa
9. The shoulder girdle and the bones of the arm: clavicle, scapula, humerus
10. Forearm and hand: radius, ulna, carpus, metacarpus, phalanges
11. The pelvic girdle and the pelvis: ilium, ischium, pubis, differences between the sexes
12. Femur, tibia and fibula: architecture of the lower limb
13. Ankle and foot: tarsus, metatarsus, phalanges, plantar arches
14. General arthrology and the major joints: shoulder, elbow, hip, knee

### Part three — Myology and movement

15. The muscles of the back and of the nape: layers, triangles, extension of the spine
16. The muscles of the thorax and the diaphragm: respiratory mechanics
17. The abdominal wall and the inguinal canal: broad muscles, sheaths, hernias
18. The muscles of the upper limb: shoulder, arm, forearm, hand
19. The muscles of the lower limb: glutei, thigh, leg, foot
20. The muscles of the head: mastication and facial expression
21. The muscles of the neck: triangles, hyoid muscles, fasciae
22. Biomechanics of movement: posture, gait, muscle chains

### Part four — Heart and circulation

23. Blood: plasma, erythrocytes, leukocytes, platelets, hemostasis
24. The heart: configuration, chambers, valves, pericardium
25. The conduction system and the cardiac cycle: from the sinoatrial node to stroke volume
26. The systemic circulation: aorta, branches, territories of supply
27. The pulmonary circulation and the fetal circulation
28. Venous return and the lymphatic system
29. Microcirculation, capillaries and regulation of pressure

### Part five — Respiratory apparatus

30. Upper airways: nose, paranasal cavities, pharynx, larynx
31. Trachea, bronchi and lungs: bronchial tree and segments
32. Alveoli, gas exchange, pleurae and ventilatory mechanics
33. The mediastinum: subdivisions, contents, relations

### Part six — Digestion, metabolism, excretion

34. Mouth, teeth, tongue and salivary glands
35. Pharynx and esophagus: swallowing
36. The stomach: regions, wall, glands, function
37. Small intestine and large intestine: peritoneum, mesenteries, absorption
38. Liver, biliary tracts and pancreas
39. Kidney and urinary tracts: nephron, filtration, ureters, bladder
40. Adrenal glands, homeostasis and water-salt regulation

### Part seven — Endocrinology and reproduction

41. Hypophysis, epiphysis, thyroid and parathyroids
42. The male reproductive apparatus
43. The female reproductive apparatus and the ovarian cycle
44. Pelvis and perineum: pelvic floor, triangles, sexual differences
45. Fertilization, early embryonic development and embryonic appendages

### Part eight — Nervous system and sense organs

46. The neuron, the synapse and the neuroglia
47. Spinal cord and spinal nerves: organization and reflexes
48. Brainstem and cerebellum
49. Diencephalon: thalamus, hypothalamus, limbic system
50. Telencephalon: cortex, lobes, functional areas, pathways
51. Meninges, ventricles and cerebrospinal fluid
52. The autonomic nervous system: sympathetic, parasympathetic, enteric
53. The eye and vision
54. The ear: hearing and balance
55. Smell, taste, somatic sensitivity and proprioception

---

## 3. File convention

- One file per chapter: `books/anatomia-umana/content/capitoli/NN-slug-del-titolo.md`
- `NN` is the two-digit number, from `01` to `55`.
- The file contains exactly one `#` heading and then only prose.
- The chapters are not rewritten into separate parts: `scripts/build_book.py` reassembles
  everything into `books/anatomia-umana/out/anatomia-umana.txt`, adding a title page, a spoken index and pauses.
