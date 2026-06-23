import csv
import re
from typing import List, Dict, Set
from bs4 import BeautifulSoup
from pathlib import Path
import glob


MAX_ANSWERS = 12


# ---------------------------------------------------------------------------
# ExamTopics parsers
# ---------------------------------------------------------------------------


def scrape_examtopics_page(html_content: str, source_file: str = "") -> List[Dict]:
    soup = BeautifulSoup(html_content, "html.parser")
    questions = []

    question_cards = soup.find_all("div", class_="card exam-question-card")
    print(f"  Found {len(question_cards)} question cards in {source_file}")

    for idx, card in enumerate(question_cards, 1):
        try:
            question_text = extract_question_text(card)
            if not question_text or len(question_text) < 10:
                continue

            answer_data = extract_answers(card)
            if not answer_data or not answer_data["all_answers"]:
                continue

            all_answers = answer_data["all_answers"]
            correct_answers = answer_data["correct_answers"]

            if not correct_answers:
                correct_answers = [all_answers[0]]

            is_multiple = len(correct_answers) > 1

            questions.append(
                {
                    "question": question_text,
                    "all_answers": all_answers,
                    "correct_answers": correct_answers,
                    "is_multiple": is_multiple,
                    "answer_explanations": {},
                    "explanation": "",  # ExamTopics has no explanations
                    "tags": "snowpro-advanced-architect examtopics",
                    "source_file": source_file,
                }
            )

        except Exception as e:
            print(f"    Question {idx}: Error - {e}")
            continue

    return questions


def extract_question_text(card) -> str:
    question_elem = card.find("p", class_="card-text")

    if not question_elem:
        choices_container = card.find("div", class_="question-choices-container")
        if choices_container:
            question_elem = choices_container.find_previous_sibling(["p", "div"])

    if not question_elem:
        question_elem = card.find("p")

    if question_elem:
        text = question_elem.get_text(strip=True)
        text = re.sub(r"^Question\s*#?\d+:?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^Topic\s+\d+:?\s*", "", text, flags=re.IGNORECASE)
        return text

    return ""


def extract_answers(card) -> Dict:
    all_answers = []
    correct_answers = []

    choices_container = card.find("div", class_="question-choices-container")
    if not choices_container:
        return {"all_answers": [], "correct_answers": []}

    choice_items = choices_container.find_all("li", class_="multi-choice-item")

    for item in choice_items:
        letter_span = item.find("span", class_="multi-choice-letter")
        if letter_span:
            letter_span.decompose()

        for badge in item.find_all("span", class_="badge"):
            badge.decompose()

        ans_text = item.get_text(strip=True)
        if not ans_text or len(ans_text) < 2:
            continue

        all_answers.append(ans_text)

        item_classes = item.get("class", [])
        if "correct-choice" in item_classes or "correct-hidden" in item_classes:
            correct_answers.append(ans_text)

    return {"all_answers": all_answers, "correct_answers": correct_answers}


# ---------------------------------------------------------------------------
# Udemy parser
# ---------------------------------------------------------------------------


def scrape_udemy_page(html_content: str, source_file: str = "") -> List[Dict]:
    """
    Extract questions from a Udemy practice-test results HTML page.

    Structure:
      <div class="result-pane--question-result-pane--...">
        <div id="question-prompt">                            ← question text
        <div class="result-pane--answer-result-pane--...">   ← one per answer
          <div class="answer-result-pane--answer-correct--...">  ← correct wrapper
          OR
          <div class="answer-result-pane--answer-skipped--...">  ← other wrapper
            <div id="answer-text">                           ← answer text
            <div id="question-explanation">                  ← per-answer explanation
        <div id="overall-explanation">                       ← overall explanation
    """
    soup = BeautifulSoup(html_content, "html.parser")
    questions = []

    question_blocks = soup.find_all(
        "div", class_=lambda c: c and "result-pane--question-result-pane--" in c
    )

    print(f"  Found {len(question_blocks)} question blocks in {source_file}")

    for idx, block in enumerate(question_blocks, 1):
        try:
            # --- Question text ---
            question_prompt = block.find(id="question-prompt")
            if not question_prompt:
                print(f"    Question {idx}: No question prompt found, skipping")
                continue

            question_text = question_prompt.get_text(separator=" ", strip=True)
            question_text = re.sub(r"\s+", " ", question_text).strip()
            if not question_text or len(question_text) < 10:
                continue

            # --- Answers + per-answer explanations ---
            all_answers: List[str] = []
            correct_answers: List[str] = []
            answer_explanations: Dict[str, str] = {}

            answer_panes = block.find_all(
                "div",
                class_=lambda c: c and "result-pane--answer-result-pane--" in c,
            )

            for pane in answer_panes:
                answer_text_div = pane.find(id="answer-text")
                if not answer_text_div:
                    continue

                ans_text = answer_text_div.get_text(separator=" ", strip=True)
                ans_text = re.sub(r"\s+", " ", ans_text).strip()
                if not ans_text or len(ans_text) < 2:
                    continue

                all_answers.append(ans_text)

                is_correct = bool(
                    pane.find(
                        "div",
                        class_=lambda c: c
                        and "answer-result-pane--answer-correct--" in c,
                    )
                )
                if is_correct:
                    correct_answers.append(ans_text)

                # Per-answer explanation (id="question-explanation")
                explanation_div = pane.find(id="question-explanation")
                if explanation_div:
                    explanation_text = explanation_div.get_text(
                        separator=" ", strip=True
                    )
                    explanation_text = re.sub(r"\s+", " ", explanation_text).strip()
                    if explanation_text:
                        answer_explanations[ans_text] = explanation_text

            if not all_answers:
                print(f"    Question {idx}: No answers found, skipping")
                continue

            if not correct_answers:
                print(
                    f"    Question {idx}: No correct answer found, defaulting to first"
                )
                correct_answers = [all_answers[0]]

            # --- Overall explanation ---
            overall_explanation = ""
            overall_div = block.find(id="overall-explanation")
            if overall_div:
                overall_explanation = overall_div.get_text(separator=" ", strip=True)
                overall_explanation = re.sub(
                    r"\s+", " ", overall_explanation
                ).strip()

            combined_explanation = (
                f"OVERALL: {overall_explanation}" if overall_explanation else ""
            )

            is_multiple = len(correct_answers) > 1

            questions.append(
                {
                    "question": question_text,
                    "all_answers": all_answers,
                    "correct_answers": correct_answers,
                    "is_multiple": is_multiple,
                    "answer_explanations": answer_explanations,
                    "explanation": combined_explanation,
                    "tags": "udemy",
                    "source_file": source_file,
                }
            )

        except Exception as e:
            print(f"    Question {idx}: Error - {e}")
            continue

    return questions


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------


def detect_source(html_content: str) -> str:
    if "result-pane--question-result-pane--" in html_content:
        return "udemy"
    if "exam-question-card" in html_content:
        return "examtopics"
    return "examtopics"


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text.strip().lower())
    text = re.sub(r"[^\w\s]", "", text)
    return text[:200]


def reorder_answers_for_anki(
    all_answers: List[str], correct_answers: List[str]
) -> List[str]:
    if len(all_answers) <= MAX_ANSWERS:
        return all_answers

    correct = [a for a in all_answers if a in correct_answers]
    wrong = [a for a in all_answers if a not in correct_answers]
    slots_remaining = MAX_ANSWERS - len(correct)

    if slots_remaining < 0:
        print(
            f"    Warning: Question has {len(correct)} correct answers,"
            f" truncating to {MAX_ANSWERS}"
        )
        return correct[:MAX_ANSWERS]

    return correct + wrong[:slots_remaining]


def scrape_from_files(html_files: List[str]) -> List[Dict]:
    all_questions = []
    seen_questions: Set[str] = set()

    print(f"\n{'='*60}")
    print(f"Processing {len(html_files)} HTML file(s)")
    print(f"{'='*60}\n")

    for html_file in html_files:
        print(f"📄 Processing: {html_file}")

        try:
            with open(html_file, "r", encoding="utf-8") as f:
                html_content = f.read()

            source = detect_source(html_content)
            print(f"  Detected format: {source}")

            if source == "udemy":
                questions = scrape_udemy_page(html_content, Path(html_file).name)
            else:
                questions = scrape_examtopics_page(html_content, Path(html_file).name)

            before_dedup = len(questions)
            unique_questions = []
            for q in questions:
                key = normalize_text(q["question"])
                if key not in seen_questions:
                    seen_questions.add(key)
                    unique_questions.append(q)

            duplicates = before_dedup - len(unique_questions)
            if duplicates > 0:
                print(f"    Removed {duplicates} duplicate(s)")

            all_questions.extend(unique_questions)
            print(f"  ✓ Added {len(unique_questions)} unique questions")

        except Exception as e:
            print(f"  ✗ Error processing {html_file}: {e}")

    return all_questions


# ---------------------------------------------------------------------------
# Anki CSV export
# ---------------------------------------------------------------------------


def create_anki_csv(
    questions: List[Dict], output_file: str = "examtopics_deck.csv"
):
    answer_fields = [f"Q_{i}" for i in range(1, MAX_ANSWERS + 1)]
    explanation_fields = [f"E_{i}" for i in range(1, MAX_ANSWERS + 1)]

    with open(output_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "Question",          # Field 1
                "QType",             # Field 2  (1=multiple, 2=single)
                "Answers",           # Field 3  (e.g. "1 0 0 1 0 ...")
                *answer_fields,      # Fields 4-15  (Q_1 … Q_12)
                *explanation_fields, # Fields 16-27 (E_1 … E_12)
                "Explanation",       # Field 28 (overall)
                "Tags",              # Field 29
            ]
        )

        single_count = 0
        multiple_count = 0
        truncated_count = 0

        for q in questions:
            question = q["question"]
            all_answers = q["all_answers"]
            correct_answers = q["correct_answers"]
            answer_explanations = q.get("answer_explanations", {})
            is_multiple = q["is_multiple"]
            explanation = q.get("explanation", "")
            tags = q.get("tags", "")

            if len(all_answers) > MAX_ANSWERS:
                all_answers = reorder_answers_for_anki(all_answers, correct_answers)
                truncated_count += 1

            if is_multiple:
                question = f"[SELECT {len(correct_answers)}] {question}"
                tags += " multiple-answer"
                multiple_count += 1
            else:
                single_count += 1

            answer_flags = [
                "1" if ans in correct_answers else "0"
                for ans in all_answers[:MAX_ANSWERS]
            ]
            answer_string = " ".join(answer_flags)

            qtype = "1" if is_multiple else "2"

            ans_cells = [
                all_answers[i] if i < len(all_answers) else ""
                for i in range(MAX_ANSWERS)
            ]
            exp_cells = [
                answer_explanations.get(all_answers[i], "")
                if i < len(all_answers)
                else ""
                for i in range(MAX_ANSWERS)
            ]

            row = [
                question,
                qtype,
                answer_string,
                *ans_cells,
                *exp_cells,
                explanation,
                tags,
            ]
            writer.writerow(row)

        print(f"\n{'='*60}")
        print(f"✓ Created {len(questions)} unique cards in {output_file}")
        print(f"  - Single answer questions:           {single_count}")
        print(f"  - Multiple answer questions:         {multiple_count}")
        if truncated_count > 0:
            print(
                f"  - Questions with >{MAX_ANSWERS} choices (reordered): {truncated_count}"
            )
        print(f"{'='*60}")


# ---------------------------------------------------------------------------
# Review / preview helpers
# ---------------------------------------------------------------------------


def preview_questions(questions: List[Dict], count: int = 3):
    print("\n" + "=" * 60)
    print("PREVIEW OF EXTRACTED QUESTIONS")
    print("=" * 60)

    for i, q in enumerate(questions[:count], 1):
        print(f"\n--- Question {i} ---")
        print(f"Source: {q.get('source_file', 'Unknown')}")
        print(f"Type: {'MULTIPLE CHOICE' if q['is_multiple'] else 'SINGLE CHOICE'}")
        print(
            f"Q: {q['question'][:200]}"
            f"{'...' if len(q['question']) > 200 else ''}"
        )
        print(f"\nAnswers ({len(q['all_answers'])} total):")
        answer_explanations = q.get("answer_explanations", {})
        for j, ans in enumerate(q["all_answers"], 1):
            marker = "✓✓✓" if ans in q["correct_answers"] else "   "
            print(
                f"  {marker} {chr(64+j)}. {ans[:100]}"
                f"{'...' if len(ans) > 100 else ''}"
            )
            exp = answer_explanations.get(ans, "")
            if exp:
                print(
                    f"         ↳ {exp[:120]}"
                    f"{'...' if len(exp) > 120 else ''}"
                )
        print(f"\nCorrect answers: {len(q['correct_answers'])}")
        if q.get("explanation"):
            print(
                f"\nExplanation: {q['explanation'][:300]}"
                f"{'...' if len(q['explanation']) > 300 else ''}"
            )


def export_summary(
    questions: List[Dict], output_file: str = "questions_summary.txt"
):
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"Total Questions: {len(questions)}\n")
        f.write("=" * 80 + "\n\n")

        for i, q in enumerate(questions, 1):
            f.write(
                f"Question {i} (from {q.get('source_file', 'Unknown')}):\n"
            )
            f.write(f"Type: {'MULTIPLE' if q['is_multiple'] else 'SINGLE'}\n")
            f.write(f"{q['question']}\n\n")

            answer_explanations = q.get("answer_explanations", {})
            for j, ans in enumerate(q["all_answers"], 1):
                marker = "[✓]" if ans in q["correct_answers"] else "[ ]"
                f.write(f"  {marker} {chr(64+j)}. {ans}\n")
                exp = answer_explanations.get(ans, "")
                if exp:
                    f.write(f"       ↳ {exp}\n")

            if q.get("explanation"):
                f.write(f"\nExplanation:\n{q['explanation']}\n")

            f.write("\n" + "-" * 80 + "\n\n")

    print(f"✓ Summary exported to {output_file}")


def find_html_files(pattern: str = "*.html") -> List[str]:
    files = glob.glob(pattern)
    print(files)
    return sorted(files)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("ExamTopics / Udemy to Anki Converter - Multi-File Edition")
    print("=" * 60)

    html_files = find_html_files("*.html")

    if not html_files:
        print(f"\n⚠ No HTML files found!")
        print("\n📋 INSTRUCTIONS:")
        print("=" * 60)
        print("Supported formats:")
        print("  • ExamTopics — save the page after revealing correct answers")
        print("  • Udemy      — save the practice-test results page")
        print("\n1. Save your HTML files into the same folder as this script")
        print("2. Run the script — the format is detected automatically")
        print("\nOR specify files manually in the script:")
        print('  html_files = ["file1.html", "file2.html"]')
        print("=" * 60)

    else:
        print(f"\nFound {len(html_files)} HTML file(s):")
        for f in html_files:
            print(f"  - {f}")

        questions = scrape_from_files(html_files)

        if questions:
            preview_questions(questions, count=3)
            create_anki_csv(questions, "snowpro_architect.csv")
            export_summary(questions, "questions_summary.txt")

            print("\n" + "=" * 60)
            print("📥 NEXT STEPS")
            print("=" * 60)
            print("1. Review questions_summary.txt to verify extraction")
            print("2. Open Anki")
            print("3. File → Import → snowpro_architect.csv")
            print("4. Settings:")
            print("   - Field separator: Comma")
            print("   - Note type: AllInOne (Multiple Choice for Anki)")
            print("5. Map fields:")
            print("   - Field  1 → Question")
            print("   - Field  2 → QType")
            print("   - Field  3 → Answers")
            for i in range(1, MAX_ANSWERS + 1):
                print(f"   - Field {3+i:2d} → Q_{i}")
            for i in range(1, MAX_ANSWERS + 1):
                print(f"   - Field {15+i:2d} → E_{i}")
            print(f"   - Field {16+MAX_ANSWERS:2d} → Explanation")
            print(f"   - Field {17+MAX_ANSWERS:2d} → Tags")
            print("\n💡 Note: Questions with [SELECT N] require multiple answers")
            print("=" * 60)

        else:
            print("\n⚠ No questions extracted from any file!")
            print("\nTroubleshooting:")
            print("  ExamTopics: make sure answers are revealed before saving")
            print("  Udemy: save the results page after completing the quiz")