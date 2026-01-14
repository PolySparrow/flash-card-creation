import csv
import re
from typing import List, Dict, Set
from bs4 import BeautifulSoup
from pathlib import Path
import glob


def scrape_examtopics_page(html_content: str, source_file: str = "") -> List[Dict]:
    """
    Extract questions from ExamTopics HTML.
    Handles both single and multiple correct answers.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    questions = []
    
    # Find all question cards
    question_cards = soup.find_all('div', class_='card exam-question-card')
    
    print(f"  Found {len(question_cards)} question cards in {source_file}")
    
    for idx, card in enumerate(question_cards, 1):
        try:
            # Extract question text
            question_text = extract_question_text(card)
            if not question_text or len(question_text) < 10:
                continue
            
            # Extract answers from question-choices-container
            answer_data = extract_answers(card)
            if not answer_data or not answer_data['all_answers']:
                continue
            
            all_answers = answer_data['all_answers']
            correct_answers = answer_data['correct_answers']
            
            if not correct_answers:
                # Still include it, but mark as needing review
                correct_answers = [all_answers[0]]  # Default to first answer
            
            # Determine if multiple choice
            is_multiple = len(correct_answers) > 1
            
            # Build question dict
            question_dict = {
                'question': question_text,
                'all_answers': all_answers,
                'correct_answers': correct_answers,
                'is_multiple': is_multiple,
                'tags': 'snowpro-advanced-architect examtopics',
                'source_file': source_file  # Track which file this came from
            }
            
            questions.append(question_dict)
            
        except Exception as e:
            print(f"    Question {idx}: Error - {e}")
            continue
    
    return questions


def normalize_text(text: str) -> str:
    """Normalize text for duplicate detection"""
    # Remove extra whitespace, lowercase, remove punctuation
    text = re.sub(r'\s+', ' ', text.strip().lower())
    text = re.sub(r'[^\w\s]', '', text)
    return text[:200]  # Use first 200 chars for comparison


def extract_question_text(card) -> str:
    """Extract question text from card"""
    # The question text is usually in a p tag with class 'card-text'
    question_elem = card.find('p', class_='card-text')
    
    if not question_elem:
        # Try alternative: find the text before the choices container
        choices_container = card.find('div', class_='question-choices-container')
        if choices_container:
            # Get all text before the choices container
            question_elem = choices_container.find_previous_sibling(['p', 'div'])
    
    if not question_elem:
        # Last resort: find any p tag in the card
        question_elem = card.find('p')
    
    if question_elem:
        text = question_elem.get_text(strip=True)
        # Remove "Question #X" prefix if present
        text = re.sub(r'^Question\s*#?\d+:?\s*', '', text, flags=re.IGNORECASE)
        # Remove "Topic X" prefix if present
        text = re.sub(r'^Topic\s+\d+:?\s*', '', text, flags=re.IGNORECASE)
        return text
    
    return ""


def extract_answers(card) -> Dict:
    """
    Extract all answers and identify correct ones from question-choices-container.
    Only extracts the answer text, excluding the letter prefix and badges.
    """
    all_answers = []
    correct_answers = []
    
    # Find the question-choices-container
    choices_container = card.find('div', class_='question-choices-container')
    
    if not choices_container:
        return {'all_answers': [], 'correct_answers': []}
    
    # Find all multi-choice-item elements
    choice_items = choices_container.find_all('li', class_='multi-choice-item')
    
    for item in choice_items:
        # Remove the letter span (e.g., "A.", "B.", etc.)
        letter_span = item.find('span', class_='multi-choice-letter')
        if letter_span:
            letter_span.decompose()  # Remove from the tree
        
        # Remove badges (e.g., "Most Voted")
        badges = item.find_all('span', class_='badge')
        for badge in badges:
            badge.decompose()
        
        # Get the remaining text (just the answer)
        ans_text = item.get_text(strip=True)
        
        # Skip empty answers
        if not ans_text or len(ans_text) < 2:
            continue
        
        all_answers.append(ans_text)
        
        # Check if this is a correct answer
        # Correct answers have classes: 'multi-choice-item correct-hidden correct-choice'
        item_classes = item.get('class', [])
        
        if 'correct-choice' in item_classes or 'correct-hidden' in item_classes:
            correct_answers.append(ans_text)
    
    return {
        'all_answers': all_answers,
        'correct_answers': correct_answers
    }


def reorder_answers_for_anki(all_answers: List[str], correct_answers: List[str]) -> List[str]:
    """
    Reorder answers to ensure all correct answers are in the first 5 choices.
    Keeps the order otherwise intact.
    """
    if len(all_answers) <= 5:
        # No reordering needed if 5 or fewer answers
        return all_answers
    
    # Separate correct and wrong answers
    correct = [ans for ans in all_answers if ans in correct_answers]
    wrong = [ans for ans in all_answers if ans not in correct_answers]
    
    # Calculate how many wrong answers we can include
    slots_remaining = 5 - len(correct)
    
    if slots_remaining < 0:
        # Edge case: more than 5 correct answers (shouldn't happen in practice)
        print(f"    Warning: Question has {len(correct)} correct answers, truncating to 5")
        return correct[:5]
    
    # Take the first N wrong answers to fill remaining slots
    reordered = correct + wrong[:slots_remaining]
    
    return reordered


def scrape_from_files(html_files: List[str]) -> List[Dict]:
    """Load and parse HTML from multiple files"""
    all_questions = []
    seen_questions = set()  # For global duplicate detection
    
    print(f"\n{'='*60}")
    print(f"Processing {len(html_files)} HTML file(s)")
    print(f"{'='*60}\n")
    
    for html_file in html_files:
        print(f"📄 Processing: {html_file}")
        
        try:
            with open(html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            questions = scrape_examtopics_page(html_content, Path(html_file).name)
            
            # Remove duplicates across all files
            before_dedup = len(questions)
            unique_questions = []
            
            for q in questions:
                normalized_q = normalize_text(q['question'])
                if normalized_q not in seen_questions:
                    seen_questions.add(normalized_q)
                    unique_questions.append(q)
            
            duplicates = before_dedup - len(unique_questions)
            if duplicates > 0:
                print(f"    Removed {duplicates} duplicate(s)")
            
            all_questions.extend(unique_questions)
            print(f"  ✓ Added {len(unique_questions)} unique questions")
            
        except Exception as e:
            print(f"  ✗ Error processing {html_file}: {e}")
    
    return all_questions


def create_anki_csv(questions: List[Dict], output_file: str = "examtopics_deck.csv"):
    """
    Create Anki-compatible CSV for Multiple Choice add-on.
    Handles both single and multiple correct answers.
    Ensures correct answers are always in the first 5 choices.
    """
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        # Header row (column names)
        writer.writerow(
            [
                "Question",   # Field 1
                "QType",      # Field 2 (1=multiple, 2=Single)
                "Answers",    # Field 3 (e.g., "1 0 0 1 0")
                "Q_1",        # Field 4
                "Q_2",        # Field 5
                "Q_3",        # Field 6
                "Q_4",        # Field 7
                "Q_5",        # Field 8
                "Tags",       # Field 9
            ]
        )
        single_count = 0
        multiple_count = 0
        truncated_count = 0
        
        for q in questions:
            question = q['question']
            all_answers = q['all_answers']
            correct_answers = q['correct_answers']
            is_multiple = q['is_multiple']
            tags = q.get('tags', '')
            
            # Reorder to ensure correct answers are in first 5
            if len(all_answers) > 5:
                all_answers = reorder_answers_for_anki(all_answers, correct_answers)
                truncated_count += 1
            
            # Add indicator if multiple answers required
            if is_multiple:
                question = f"[SELECT {len(correct_answers)}] {question}"
                tags += ' multiple-answer'
                multiple_count += 1
            else:
                single_count += 1
            
            # Build answer string
            # "1" for correct answers, "0" for wrong answers
            answer_flags = []
            for ans in all_answers[:5]:  # Max 5 answers
                if ans in correct_answers:
                    answer_flags.append('1')
                else:
                    answer_flags.append('0')
            
            answer_string = ' '.join(answer_flags)
            
            # Determine QType
            # 2 = Single choice (radio buttons)
            # 3 = Multiple choice (checkboxes)
            qtype = '1' if is_multiple else '2'
            
            # Build row - pad with empty strings if less than 5 answers
            row = [
                question,
                qtype,
                answer_string,
                all_answers[0] if len(all_answers) > 0 else '',
                all_answers[1] if len(all_answers) > 1 else '',
                all_answers[2] if len(all_answers) > 2 else '',
                all_answers[3] if len(all_answers) > 3 else '',
                all_answers[4] if len(all_answers) > 4 else '',
                tags
            ]
            
            writer.writerow(row)
        
        print(f"\n{'='*60}")
        print(f"✓ Created {len(questions)} unique cards in {output_file}")
        print(f"  - Single answer questions: {single_count}")
        print(f"  - Multiple answer questions: {multiple_count}")
        if truncated_count > 0:
            print(f"  - Questions with >5 choices (reordered): {truncated_count}")
        print(f"{'='*60}")


def preview_questions(questions: List[Dict], count: int = 3):
    """Preview first few questions"""
    print("\n" + "=" * 60)
    print("PREVIEW OF EXTRACTED QUESTIONS")
    print("=" * 60)
    
    for i, q in enumerate(questions[:count], 1):
        print(f"\n--- Question {i} ---")
        print(f"Source: {q.get('source_file', 'Unknown')}")
        print(f"Type: {'MULTIPLE CHOICE' if q['is_multiple'] else 'SINGLE CHOICE'}")
        print(f"Q: {q['question'][:200]}{'...' if len(q['question']) > 200 else ''}")
        print(f"\nAnswers ({len(q['all_answers'])} total):")
        for j, ans in enumerate(q['all_answers'], 1):
            marker = "✓✓✓" if ans in q['correct_answers'] else "   "
            print(f"  {marker} {chr(64+j)}. {ans[:100]}{'...' if len(ans) > 100 else ''}")
        print(f"\nCorrect answers: {len(q['correct_answers'])}")


def export_summary(questions: List[Dict], output_file: str = "questions_summary.txt"):
    """Export a summary of all questions for review"""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"Total Questions: {len(questions)}\n")
        f.write("=" * 80 + "\n\n")
        
        for i, q in enumerate(questions, 1):
            f.write(f"Question {i} (from {q.get('source_file', 'Unknown')}):\n")
            f.write(f"Type: {'MULTIPLE' if q['is_multiple'] else 'SINGLE'}\n")
            f.write(f"{q['question']}\n\n")
            
            for j, ans in enumerate(q['all_answers'], 1):
                marker = "[✓]" if ans in q['correct_answers'] else "[ ]"
                f.write(f"  {marker} {chr(64+j)}. {ans}\n")
            
            f.write("\n" + "-" * 80 + "\n\n")
    
    print(f"✓ Summary exported to {output_file}")


def find_html_files(pattern: str = "*.html") -> List[str]:
    """Find all HTML files matching the pattern"""
    files = glob.glob(pattern)
    print(files)
    return sorted(files)


# Main workflow
if __name__ == "__main__":
    
    print("=" * 60)
    print("ExamTopics to Anki Converter - Multi-File Edition")
    print("Snowflake SnowPro Advanced Architect")
    print("=" * 60)
    
    # Find all HTML files in current directory
    html_files = find_html_files("*.html")
    
    # Alternative: Specify files manually
    # html_files = ["exam_page1.html", "exam_page2.html", "exam_page3.html"]
    
    # Alternative: Find files with specific pattern
    # html_files = find_html_files("exam_*.html")
    
    if not html_files:
        print(f"\n⚠ No HTML files found!")
        print("\n📋 INSTRUCTIONS:")
        print("=" * 60)
        print("1. Save your ExamTopics pages as HTML files")
        print("2. Name them anything.html (e.g., page1.html, page2.html, etc.)")
        print("3. Place all files in the same folder as this script")
        print("\nOR")
        print("\nEdit the script to specify files manually:")
        print('  html_files = ["file1.html", "file2.html"]')
        print("\nOR")
        print("\nUse a pattern to match specific files:")
        print('  html_files = find_html_files("exam_*.html")')
        print("=" * 60)
        
    else:
        print(f"\nFound {len(html_files)} HTML file(s):")
        for f in html_files:
            print(f"  - {f}")
        
        # Process all files
        questions = scrape_from_files(html_files)
        
        if questions:
            # Preview
            preview_questions(questions, count=3)
            
            # Create Anki deck
            create_anki_csv(questions, "snowpro_architect.csv")
            
            # Export summary for review
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
            print("   - Field 1 → Question")
            print("   - Field 2 → QType")
            print("   - Field 3 → Answers")
            print("   - Field 4 → Q_1")
            print("   - Field 5 → Q_2")
            print("   - Field 6 → Q_3")
            print("   - Field 7 → Q_4")
            print("   - Field 8 → Q_5")
            print("   - Field 9 → Tags")
            print("\n💡 Note: Questions with [SELECT N] require multiple answers")
            print("=" * 60)
            
        else:
            print("\n⚠ No questions extracted from any file!")
            print("\nTroubleshooting:")
            print("1. Make sure you're logged into ExamTopics when saving")
            print("2. Make sure answers are revealed (click to show correct answers)")
            print("3. Save pages AFTER all content is loaded")
            print("4. Check if the page structure has changed")