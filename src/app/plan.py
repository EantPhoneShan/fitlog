"""The starting plan every new account gets. Each user can change it on the Plan screen.

It is Adam's plan v2, which works as a sensible default for anyone cutting fat
while building muscle on ~30-40 minute gym sessions.
"""

import copy

DEFAULT_TARGETS = {
    "calories": 1900,
    "protein": 135,  # grams
    "water": 3.0,  # litres
    "steps": 4000,
    "sleep": 7.0,  # hours
}

# Monday first, Sunday last (same order as Python's date.weekday())
DEFAULT_SPLIT = [
    {"name": "Push", "exercises": [
        "Incline DB / machine press + lateral raise (4 sets)",
        "Shoulder press + overhead triceps extension",
        "Cable crunch",
    ]},
    {"name": "Pull", "exercises": [
        "Lat pulldown / pull-ups + incline or Bayesian curl",
        "Cable row + face pull",
        "Hammer curl",
    ]},
    {"name": "Legs", "exercises": [
        "Leg press / goblet squat + hanging knee raise",
        "RDL / leg curl + calf raise",
        "Bulgarian split squat",
    ]},
    {"name": "Rest", "exercises": ["Rest day. Hit protein, water and your steps."]},
    {"name": "Upper", "exercises": [
        "Pull-ups / pulldown + flat DB / machine press",
        "Chest-supported row + lateral raise (4 sets)",
        "Curl + triceps pushdown",
    ]},
    {"name": "Lower", "exercises": [
        "Reverse lunge / leg press + hip thrust",
        "Leg curl + core circuit",
        "8-minute indoor finisher",
    ]},
    {"name": "Rest", "exercises": ["Rest day. Weekly check-in: measure your waist at the belly button."]},
]

DEFAULT_MENU = [
    {"meal": "Breakfast", "food": "50 g oats + 250 ml milk + 1 scoop whey + banana", "protein": 39},
    {"meal": "Lunch", "food": "150 g raw chicken + 1 egg + 1 cup rice + 100 g carrot/okra", "protein": 46},
    {"meal": "Snack", "food": "150 g yogurt + 100 g grapes", "protein": 8},
    {"meal": "Dinner", "food": "150 g shrimp + 1 egg, or 150 g tofu + 2 eggs, + rice + veg", "protein": 38},
]

RULES = [
    "Losing 0.3-0.5 kg a week: keep going.",
    "Flat for 2 weeks: cut 150-200 kcal or add a 10-min incline walk on gym days.",
    "Losing more than 1 kg a week: eat a bit more.",
    "Judge by 7-day averages, not single weigh-ins.",
    "Double progression, 1-2 reps in reserve, deload every 7th week.",
]

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def default_settings() -> dict:
    return copy.deepcopy({"targets": DEFAULT_TARGETS, "split": DEFAULT_SPLIT, "menu": DEFAULT_MENU})
