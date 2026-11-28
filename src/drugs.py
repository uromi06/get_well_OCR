"""Small reference list of common active ingredients (German spelling).

Used for two things:
  1. Spelling suggestions in the review screen ("Glimeprid" -> "Glimepirid").
  2. The "used for" line on the patient plan (common use only; the doctor checks).

Extend the list freely. Keys must be the German INN spelling.
"""
from rapidfuzz import fuzz, process

# active ingredient -> common-use category (see PURPOSES in export.py)
DRUGS = {
    # blood pressure / heart
    "Ramipril": "bp", "Lisinopril": "bp", "Enalapril": "bp", "Perindopril": "bp", "Candesartan": "bp",
    "Valsartan": "bp", "Losartan": "bp", "Olmesartan": "bp", "Telmisartan": "bp", "Irbesartan": "bp",
    "Amlodipin": "bp", "Lercanidipin": "bp", "Nitrendipin": "bp", "Moxonidin": "bp", "Doxazosin": "bp",
    "Sacubitril/Valsartan": "heart", "Metoprolol": "heart", "Metoprololsuccinat": "heart",
    "Bisoprolol": "heart", "Carvedilol": "heart", "Nebivolol": "heart", "Digoxin": "heart",
    "Digitoxin": "heart", "Amiodaron": "heart", "Ivabradin": "heart", "Verapamil": "heart",
    "Diltiazem": "heart", "Ranolazin": "heart", "Nitroglycerin": "heart", "ISDN": "heart",
    "Molsidomin": "heart",
    # water tablets
    "Torasemid": "water", "Furosemid": "water", "Hydrochlorothiazid": "water", "HCT": "water",
    "Chlortalidon": "water", "Xipamid": "water", "Indapamid": "water", "Spironolacton": "water",
    "Eplerenon": "water", "Finerenon": "water",
    # blood thinners
    "ASS": "thin", "Acetylsalicylsäure": "thin", "Clopidogrel": "thin", "Prasugrel": "thin",
    "Ticagrelor": "thin", "Apixaban": "thin", "Rivaroxaban": "thin", "Edoxaban": "thin",
    "Dabigatran": "thin", "Phenprocoumon": "thin", "Warfarin": "thin", "Enoxaparin": "thin",
    "Heparin": "thin",
    # cholesterol
    "Atorvastatin": "chol", "Simvastatin": "chol", "Rosuvastatin": "chol", "Pravastatin": "chol",
    "Ezetimib": "chol", "Bempedoinsäure": "chol",
    # diabetes
    "Metformin": "sugar", "Glimepirid": "sugar", "Glibenclamid": "sugar", "Empagliflozin": "sugar",
    "Dapagliflozin": "sugar", "Sitagliptin": "sugar", "Vildagliptin": "sugar", "Saxagliptin": "sugar",
    "Linagliptin": "sugar", "Pioglitazon": "sugar", "Liraglutid": "sugar", "Dulaglutid": "sugar",
    "Semaglutid": "sugar", "Tirzepatid": "sugar", "Insulin lispro": "sugar", "Insulin aspart": "sugar",
    "Insulin glulisin": "sugar", "Insulin glargin": "sugar", "Insulin detemir": "sugar",
    "Insulin degludec": "sugar", "Humaninsulin": "sugar", "NPH-Insulin": "sugar", "Glucagon": "sugar",
    # stomach
    "Pantoprazol": "stomach", "Omeprazol": "stomach", "Esomeprazol": "stomach", "Lansoprazol": "stomach",
    "Famotidin": "stomach",
    # thyroid
    "L-Thyroxin": "thyroid", "Thiamazol": "thyroid", "Carbimazol": "thyroid",
    # pain
    "Paracetamol": "pain", "Ibuprofen": "pain", "Metamizol": "pain", "Diclofenac": "pain",
    "Naproxen": "pain", "Celecoxib": "pain", "Etoricoxib": "pain", "Tramadol": "pain", "Tilidin": "pain",
    "Morphin": "pain", "Hydromorphon": "pain", "Oxycodon": "pain", "Tapentadol": "pain", "Fentanyl": "pain",
    "Buprenorphin": "pain", "Pregabalin": "pain", "Gabapentin": "pain",
    # gout
    "Allopurinol": "gout", "Febuxostat": "gout", "Colchicin": "gout",
    # no category on the patient plan (doctor fills in): lungs, brain, others
    "Salbutamol": None, "Formoterol": None, "Salmeterol": None, "Tiotropium": None, "Budesonid": None,
    "Beclometason": None, "Fluticason": None, "Montelukast": None, "Prednisolon": None,
    "Hydrocortison": None, "Dexamethason": None, "Levetiracetam": None, "Lamotrigin": None,
    "Valproinsäure": None, "Carbamazepin": None, "Levodopa": None, "Donepezil": None, "Memantin": None,
    "Sertralin": None, "Citalopram": None, "Escitalopram": None, "Mirtazapin": None, "Venlafaxin": None,
    "Duloxetin": None, "Amitriptylin": None, "Quetiapin": None, "Risperidon": None, "Haloperidol": None,
    "Melperon": None, "Pipamperon": None, "Lorazepam": None, "Diazepam": None, "Zopiclon": None,
    "Tamsulosin": None, "Finasterid": None, "Solifenacin": None, "Mirabegron": None, "Alendronsäure": None,
    "Denosumab": None, "Colecalciferol": None, "Calcium": None, "Kaliumchlorid": None, "Magnesium": None,
    "Eisen(II)-sulfat": None, "Folsäure": None, "Cyanocobalamin": None, "Macrogol": None,
    "Lactulose": None, "Metoclopramid": None, "Ondansetron": None, "Amoxicillin": None,
    "Ampicillin/Sulbactam": None, "Piperacillin/Tazobactam": None, "Cefuroxim": None, "Ceftriaxon": None,
    "Ciprofloxacin": None, "Levofloxacin": None, "Clarithromycin": None, "Doxycyclin": None,
    "Cotrimoxazol": None, "Nitrofurantoin": None, "Fosfomycin": None, "Methotrexat": None,
    # transplant / immunosuppression and their usual companions
    "Tacrolimus": None, "Ciclosporin": None, "Everolimus": None, "Sirolimus": None,
    "Mycophenolatmofetil": None, "Mycophenolsäure": None, "Azathioprin": None, "Belatacept": None,
    "Valganciclovir": None, "Ganciclovir": None, "Fluconazol": None, "Voriconazol": None,
}

# brand names and other spellings -> active ingredient (what the summary shows)
ALIASES = {
    "Levothyroxin": "L-Thyroxin", "Euthyrox": "L-Thyroxin", "L-Thyrox": "L-Thyroxin", "Marcumar": "Phenprocoumon",
    "Falithrom": "Phenprocoumon", "Eliquis": "Apixaban", "Xarelto": "Rivaroxaban", "Lixiana": "Edoxaban",
    "Pradaxa": "Dabigatran", "Jardiance": "Empagliflozin", "Forxiga": "Dapagliflozin", "Januvia": "Sitagliptin",
    "Amaryl": "Glimepirid", "Ozempic": "Semaglutid", "Victoza": "Liraglutid", "Trulicity": "Dulaglutid",
    "Mounjaro": "Tirzepatid", "Humalog": "Insulin lispro", "Liprolog": "Insulin lispro",
    "NovoRapid": "Insulin aspart", "Fiasp": "Insulin aspart", "Apidra": "Insulin glulisin",
    "Lantus": "Insulin glargin", "Toujeo": "Insulin glargin", "Abasaglar": "Insulin glargin",
    "Levemir": "Insulin detemir", "Tresiba": "Insulin degludec", "Baqsimi": "Glucagon", "GlucaGen": "Glucagon",
    "Entresto": "Sacubitril/Valsartan", "Torem": "Torasemid", "Lasix": "Furosemid", "Aldactone": "Spironolacton",
    "Pantozol": "Pantoprazol", "Sortis": "Atorvastatin", "Novalgin": "Metamizol", "Aspirin": "ASS",
    "Brilique": "Ticagrelor", "Plavix": "Clopidogrel", "Clexane": "Enoxaparin", "Lyrica": "Pregabalin",
    "Decortin": "Prednisolon", "Spiriva": "Tiotropium", "Movicol": "Macrogol", "Vigantol": "Colecalciferol",
    "Dekristol": "Colecalciferol", "Zyloric": "Allopurinol", "Glucophage": "Metformin",
    "Prograf": "Tacrolimus", "Advagraf": "Tacrolimus", "Envarsus": "Tacrolimus", "Modigraf": "Tacrolimus",
    "Sandimmun": "Ciclosporin", "Certican": "Everolimus", "Rapamune": "Sirolimus",
    "CellCept": "Mycophenolatmofetil", "Myfortic": "Mycophenolsäure", "Imurek": "Azathioprin",
    "Nulojix": "Belatacept", "Valcyte": "Valganciclovir", "Diflucan": "Fluconazol",
    "Cotrim": "Cotrimoxazol", "Sulfamethoxazol/Trimethoprim": "Cotrimoxazol",
}

_LOWER = {name.lower(): name for name in DRUGS}
_LOWER.update({alias.lower(): inn for alias, inn in ALIASES.items()})


def canonical(name: str) -> str | None:
    """Exact (case-insensitive) match in the list, else None."""
    return _LOWER.get((name or "").strip().lower())


def suggest(name: str, cutoff: int = 80) -> str | None:
    """Closest known drug if the name looks misspelled. None if exact or unknown."""
    name = (name or "").strip()
    if not name or canonical(name):
        return None
    match = process.extractOne(name, list(DRUGS), scorer=fuzz.WRatio, score_cutoff=cutoff)
    return match[0] if match else None


def purpose(name: str) -> str | None:
    """Common-use category for a drug name (uses the first word, e.g. 'ASS 100')."""
    key = canonical(name) or canonical((name or "").split(" ")[0])
    return DRUGS.get(key) if key else None
