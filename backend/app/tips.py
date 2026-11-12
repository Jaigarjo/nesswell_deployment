"""General, research-based tips: shown while someone's own data is still thin.

Each tip is tied to a factor and retires for a person once they have enough of their
own days on that factor to judge it personally (MIN_GROUP on each side). From then
on, their own data speaks: a personal suggestion if it shows a clear effect, nothing
if it doesn't.

Wording rules: say what the research actually found, at the strength it found it.
Observational findings say "linked to", small trials say "small trial".
"""

TIPS = [
    {
        "key": "exercise",
        "action": "Move most days",
        "why": "A review of 1,039 trials found physical activity eased symptoms of depression, "
               "anxiety and stress. Every type helped, from walking and yoga to the gym.",
        "source": "Singh et al., British Journal of Sports Medicine, 2023",
        "url": "https://bjsm.bmj.com/content/early/2023/03/02/bjsports-2022-106195",
        "short": "Research links regular movement to less anxiety and low mood.",
    },
    {
        "key": "sleep_hours",
        "action": "Aim for 7+ hours of sleep",
        "why": "Sleep experts recommend adults regularly get 7 or more hours. Getting less is "
               "linked to worse health, including depression.",
        "source": "AASM and Sleep Research Society consensus, 2015",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC4434546/",
        "short": "Sleep experts recommend 7 or more hours for adults.",
    },
    {
        "key": "alcohol",
        "action": "Go easy on drinks, especially late",
        "why": "Alcohol helps you fall asleep, but it disrupts the second half of the night "
               "and reduces REM sleep at moderate and higher amounts.",
        "source": "Ebrahim et al., Alcoholism: Clinical & Experimental Research, 2013",
        "url": "https://pubmed.ncbi.nlm.nih.gov/23347102/",
        "short": "Alcohol disrupts the second half of your night's sleep.",
    },
    {
        "key": "social",
        "action": "Make time for people",
        "why": "People report higher well-being when they have more social interactions, "
               "and deeper conversations count for more than small talk.",
        "source": "Sun, Harris & Vazire, Journal of Personality and Social Psychology, 2020",
        "url": "https://doi.org/10.1037/pspp0000272",
        "short": "More, and deeper, conversations are linked to higher well-being.",
    },
    {
        "key": "diet_quality",
        "action": "Eat more whole foods",
        "why": "In a small 12-week trial, people with depression who moved towards a "
               "Mediterranean-style diet improved more than a comparison group.",
        "source": "Jacka et al. (SMILES trial), BMC Medicine, 2017",
        "url": "https://doi.org/10.1186/s12916-017-0791-y",
        "short": "A Mediterranean-style diet helped mood in a small trial.",
    },
    {
        "key": "work_stress",
        "action": "Switch off from work after hours",
        "why": "Research on recovery from work treats mentally switching off in your free "
               "time as key to staying well, and simple techniques can help you do it.",
        "source": "Karabinski et al., Journal of Occupational Health Psychology, 2021",
        "url": "https://doi.org/10.1037/ocp0000280",
        "short": "Mentally switching off after work helps you recover.",
    },
    {
        "key": "g_steps",
        "action": "Walk 7,000+ steps a day",
        "why": "Across 33 studies of 96,000 adults, 7,000 or more daily steps was linked to a "
               "lower risk of depression. These studies show a link, not proof of cause.",
        "source": "Bizzozero-Peroni et al., JAMA Network Open, 2024",
        "url": "https://doi.org/10.1001/jamanetworkopen.2024.51208",
        "short": "7,000+ daily steps is linked to lower risk of depression.",
    },
]
