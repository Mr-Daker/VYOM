"""Grounded activity and exit-check generation with strict guardrails.

When ANTHROPIC_API_KEY and SAARTHI_LLM_MODEL are configured, a frontier model
is asked for structured JSON. The exact same validator is applied to model and
offline-template output. If the call fails, the classroom still receives a safe,
curriculum-grounded activity from the deterministic fallback.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, List, Optional

try:
    from .models import ALL_COMPETENCIES, Activity, ActivityType, ExitTicket
    from .retrieval import RetrievalError, get_curriculum_context, source_is_approved
except ImportError:
    from models import ALL_COMPETENCIES, Activity, ActivityType, ExitTicket
    from retrieval import RetrievalError, get_curriculum_context, source_is_approved


SUPPORTED_LANGUAGES = ("English", "Hindi")
SAFE_DEFAULT_MATERIALS = ["paper", "pencils", "chalk", "blackboard"]
UNSAFE_TERMS = {"weapon", "punish", "humiliate", "dangerous", "adult content"}


class GenerationError(Exception):
    pass


def _activity_id(group_id: str, competency_id: str, activity_type: ActivityType, variation: int) -> str:
    stable = f"{group_id}:{competency_id}:{activity_type.value}:{variation}"
    return "ACT-" + uuid.uuid5(uuid.NAMESPACE_URL, stable).hex[:10].upper()


def _choose_materials(available: List[str], preferred: List[str]) -> List[str]:
    chosen = [item for item in preferred if item in available]
    if chosen:
        return chosen[:3]
    low_tech = [item for item in available if item.lower() not in {"phone", "tablet", "laptop"}]
    return low_tech[:1]


def _english_template(
    competency_id: str,
    level: str,
    activity_type: ActivityType,
    available: List[str],
    variation: int,
) -> Dict[str, Any]:
    description = ALL_COMPETENCIES[competency_id].description
    physical = _choose_materials(available, ["sticks (bundles of 10)", "bottle caps", "number cards (1-100)", "chalk", "blackboard", "paper", "pencils"])
    material_text = physical[0] if physical else "fingers and spoken examples"
    variants = variation % 3

    if level == "RECOVERY":
        titles = ["Bridge the missing step", "Tens-and-ones recovery", "Check, model, retry"]
        instructions = [
            f"Build one example of {description.lower()} with {material_text}.",
            "Say what each group of ten and each one represents.",
            "Solve a second example with less teacher help, then explain the step that was previously missed.",
        ]
        expected = "Learner represents the quantities, explains the prerequisite step, and completes one correct example."
        check = "Ask the learner to solve 34 + 12 and explain the tens and ones."
    elif level == "Not yet learned":
        titles = ["See it, build it, say it", "Concrete concept launch", "Worked example launch"]
        instructions = [
            f"Watch or read one worked example of {description.lower()}.",
            f"Rebuild the example with {material_text}.",
            "Complete one similar problem and point to the step that changes the quantity.",
        ]
        expected = "Learner copies the model and completes one parallel example with a prompt."
        check = "Show one new two-digit example and ask: which digit is tens and which is ones?"
    elif level == "Developing":
        titles = ["Solve, explain, check", "Partner practice with evidence", "Two examples, one explanation"]
        instructions = [
            f"Solve two examples that practise {description.lower()}.",
            "Compare answers with a partner and explain one step aloud.",
            "If answers differ, use the material or place-value drawing to find the error.",
        ]
        expected = "Learner solves two examples and gives a place-value explanation for one answer."
        check = "Ask for one answer and one sentence explaining how it was found."
    else:
        titles = ["Create and challenge", "Apply in a new context", "Find two valid strategies"]
        instructions = [
            f"Create a short story problem that requires {description.lower()}.",
            "Solve it using a written method and a drawing or material model.",
            "Swap with a partner, check the solution, and improve any unclear wording.",
        ]
        expected = "Learner creates a valid problem, solves it, and verifies a partner's reasoning."
        check = "Check that the story, number sentence, and answer all agree."

    if activity_type == ActivityType.INDEPENDENT_WORKSHEET:
        instructions[1] = "Complete the two examples independently before checking with a partner."
    elif activity_type == ActivityType.PEER_ACTIVITY:
        instructions[1] = "Take turns: one learner solves while the other checks each step."
    elif activity_type == ActivityType.MANIPULATIVE_ACTIVITY:
        instructions[0] = f"Build each quantity with {material_text}, then complete the operation."

    return {
        "title": titles[variants],
        "objective": f"Learners will demonstrate {description.lower()} ({competency_id}).",
        "student_instructions": instructions,
        "materials_needed": physical,
        "expected_response": expected,
        "quick_check": check,
    }


def _hindi_template(data: Dict[str, Any], competency_id: str, level: str, available: List[str], variation: int) -> Dict[str, Any]:
    descriptions = {
        "N1": "20 तक वस्तुओं की गिनती",
        "N2": "संख्याओं में अधिक, कम और बराबर की तुलना",
        "N3": "दो अंकों की संख्या को दहाई और इकाई में दिखाना",
        "N4": "बिना हासिल के दो अंकों का जोड़",
        "N5": "हासिल के साथ दो अंकों का जोड़",
        "N6": "बिना उधार के दो अंकों का घटाव",
        "N7": "उधार के साथ दो अंकों का घटाव",
    }
    description = descriptions.get(competency_id, ALL_COMPETENCIES[competency_id].description)
    material = (data.get("materials_needed") or ["स्थानीय सामग्री"])[0]
    if level == "RECOVERY":
        titles = ["छूटी हुई कड़ी जोड़ें", "दहाई-इकाई पुनराभ्यास", "जाँचें, बनाएँ, फिर करें"]
        steps = [
            f"{material} से {description} का एक उदाहरण बनाएँ।",
            "हर दहाई और इकाई का अर्थ बोलकर बताएँ।",
            "दूसरा उदाहरण कम सहायता से हल करें और छूटा हुआ चरण समझाएँ।",
        ]
    elif level == "Not yet learned":
        titles = ["देखें, बनाएँ, बताएँ", "ठोस उदाहरण से शुरुआत", "उदाहरण देखकर सीखें"]
        steps = [
            f"{description} का एक हल किया हुआ उदाहरण देखें।",
            f"उसी उदाहरण को {material} से दोबारा बनाएँ।",
            "मिलता-जुलता एक सवाल हल करें और बदला हुआ चरण दिखाएँ।",
        ]
    elif level == "Developing":
        titles = ["हल करें, समझाएँ, जाँचें", "साथी के साथ अभ्यास", "दो सवाल, एक व्याख्या"]
        steps = [
            f"{description} के दो सवाल हल करें।",
            "साथी से उत्तर मिलाएँ और एक चरण बोलकर समझाएँ।",
            f"उत्तर अलग हों तो {material} से गलती खोजें।",
        ]
    else:
        titles = ["सवाल बनाएँ और चुनौती दें", "नई स्थिति में प्रयोग", "दो तरीकों से हल"]
        steps = [
            f"{description} पर एक छोटा कहानी-सवाल बनाएँ।",
            "उसे लिखित तरीके और चित्र या सामग्री से हल करें।",
            "साथी से बदलकर उत्तर जाँचें और सवाल को स्पष्ट बनाएँ।",
        ]
    data.update(
        {
            "title": titles[variation % 3],
            "objective": f"विद्यार्थी {description} का प्रमाण देंगे ({competency_id})।",
            "student_instructions": steps,
            "expected_response": "विद्यार्थी सही उदाहरण हल करेगा और एक चरण का कारण बताएगा।",
            "quick_check": "एक नया सवाल दें और विद्यार्थी से उत्तर के साथ तरीका बताने को कहें।",
        }
    )
    return data


def _call_anthropic(prompt: str) -> Optional[Dict[str, Any]]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    model = os.getenv("SAARTHI_LLM_MODEL")
    if not api_key or not model:
        return None
    body = json.dumps(
        {
            "model": model,
            "max_tokens": 900,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        method="POST",
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        text = "".join(block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text")
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(match.group(0)) if match else None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
        return None


def validate_activity(activity: Activity, available_materials: List[str], requested_duration: int) -> List[str]:
    errors: List[str] = []
    if activity.competency_id not in ALL_COMPETENCIES:
        errors.append("unknown competency")
    if not activity.objective or activity.competency_id not in activity.objective:
        errors.append("objective does not preserve the competency")
    if activity.duration_minutes != requested_duration:
        errors.append("duration does not match the rotation slot")
    unavailable = sorted(set(activity.materials_needed) - set(available_materials))
    if unavailable:
        errors.append("unavailable materials: " + ", ".join(unavailable))
    if not 1 <= len(activity.student_instructions) <= 5 or any(len(step) > 220 for step in activity.student_instructions):
        errors.append("instructions must contain 1-5 short steps")
    joined = " ".join(activity.student_instructions).lower()
    if any(term in joined for term in UNSAFE_TERMS):
        errors.append("unsafe or inappropriate instruction")
    if not activity.source_reference or not source_is_approved(activity.source_reference, activity.competency_id):
        errors.append("source is missing or not in the approved corpus")
    if re.search(r"https?://", joined):
        errors.append("unsupported external factual claim or link")
    if activity.target_level not in {"RECOVERY", "Not yet learned", "Developing", "Mastered"}:
        errors.append("unknown target level")
    return errors


def generate_activity(
    competency_id: str,
    group_mastery_level: str,
    duration: int,
    language: str,
    materials_available: List[str],
    activity_type: ActivityType,
    group_id: str = "unassigned",
    recovery_reason: str = "",
    variation: int = 0,
    max_retries: int = 2,
) -> Activity:
    if competency_id not in ALL_COMPETENCIES:
        raise GenerationError(f"unknown competency: {competency_id}")
    if language not in SUPPORTED_LANGUAGES:
        raise GenerationError(f"unsupported language: {language}")
    if not isinstance(materials_available, list) or not all(isinstance(item, str) for item in materials_available):
        raise GenerationError("materials_available must be a list of strings")
    if not 1 <= duration <= 60:
        raise GenerationError("activity duration must be between 1 and 60 minutes")

    context = get_curriculum_context(competency_id, language)
    template = _english_template(competency_id, group_mastery_level, activity_type, materials_available, variation)
    if language == "Hindi":
        template = _hindi_template(template, competency_id, group_mastery_level, materials_available, variation)

    prompt = json.dumps(
        {
            "task": "Return one low-resource classroom activity as JSON only. Keep the supplied competency and source unchanged.",
            "required_keys": ["title", "objective", "student_instructions", "materials_needed", "expected_response", "quick_check"],
            "competency_id": competency_id,
            "level": group_mastery_level,
            "activity_type": activity_type.value,
            "duration_minutes": duration,
            "language": language,
            "available_materials": materials_available,
            "approved_context": context,
        },
        ensure_ascii=False,
    )

    last_errors: List[str] = []
    for _attempt in range(max_retries):
        model_data = _call_anthropic(prompt)
        data = model_data or template
        generated_by = "anthropic" if model_data else "grounded-template"
        try:
            activity = Activity(
                id=_activity_id(group_id, competency_id, activity_type, variation),
                title=str(data["title"]).strip(),
                objective=str(data["objective"]).strip(),
                activity_type=activity_type,
                competency_id=competency_id,
                target_level=group_mastery_level,
                group_id=group_id,
                duration_minutes=duration,
                materials_needed=list(data["materials_needed"]),
                teacher_involvement_required=activity_type in {
                    ActivityType.TEACHER_LED_EXPLANATION,
                    ActivityType.GUIDED_PRACTICE,
                    ActivityType.RECOVERY_ACTIVITY,
                },
                student_instructions=list(data["student_instructions"]),
                expected_response=str(data["expected_response"]).strip(),
                quick_check=str(data["quick_check"]).strip(),
                source_reference=context["source_reference"],
                language=language,
                generated_by=generated_by,
                recovery_reason=recovery_reason,
            )
        except (KeyError, TypeError, ValueError) as exc:
            last_errors = [f"malformed structured output: {exc}"]
            continue
        last_errors = validate_activity(activity, materials_available, duration)
        if not last_errors:
            return activity
        # A model response failed. Retry once with the safe template.
        template = _english_template(competency_id, group_mastery_level, activity_type, materials_available, variation)
        if language == "Hindi":
            template = _hindi_template(template, competency_id, group_mastery_level, materials_available, variation)

    raise GenerationError("activity rejected by guardrails: " + "; ".join(last_errors))


def generate_exit_ticket(
    competency_id: str,
    group_id: str = "unassigned",
    language: str = "English",
) -> ExitTicket:
    context = get_curriculum_context(competency_id, language)
    questions = {
        "N3": ("Show 42 as tens and ones.", "How do you know?", "4 tens and 2 ones"),
        "N4": ("Solve 34 + 12.", "Circle the tens in your working.", "46"),
        "N5": ("Solve 27 + 15.", "Show where you regrouped.", "42"),
        "N6": ("Solve 58 - 24.", "Explain what happened to the tens.", "34"),
        "N7": ("Solve 52 - 27.", "Show where you borrowed.", "25"),
    }
    question, follow_up, answer = questions.get(
        competency_id,
        (f"Show one example of {ALL_COMPETENCIES[competency_id].description.lower()}.", "Explain one step.", "Teacher checks against the objective"),
    )
    if language == "Hindi":
        hindi = {
            "N3": ("42 को दहाई और इकाई में दिखाएँ।", "आपको कैसे पता?", "4 दहाई और 2 इकाई"),
            "N4": ("34 + 12 हल करें।", "अपने हल में दहाई पर गोला बनाएँ।", "46"),
            "N5": ("27 + 15 हल करें।", "हासिल वाला चरण दिखाएँ।", "42"),
            "N6": ("58 - 24 हल करें।", "बताएँ कि दहाई में क्या हुआ।", "34"),
            "N7": ("52 - 27 हल करें।", "उधार वाला चरण दिखाएँ।", "25"),
        }
        question, follow_up, answer = hindi.get(competency_id, (question, follow_up, answer))
    return ExitTicket(
        id=f"EXIT-{group_id}-{competency_id}",
        group_id=group_id,
        competency_id=competency_id,
        question=question,
        follow_up=follow_up,
        expected_answer=answer,
        language=language,
        source_reference=context["source_reference"],
    )
