"""Test consolidated strip_cot function."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from core.utils import strip_cot
from core.orchestrator import clean_transcript_content
from core.pdf_generator import _clean_cot

# Test 1: XML think tags
r = strip_cot('Hello <think>internal reasoning</think> World')
assert 'internal' not in r and 'Hello' in r and 'World' in r, f'1: {r}'

# Test 2: [THINK] envelope
r = strip_cot('Before [THINK]some thinking[/THINK] After')
assert 'some thinking' not in r and 'Before' in r and 'After' in r, f'2: {r}'

# Test 3: Self-correction trailing
r = strip_cot('Good text\n\n**Self-Correction/Verification against Constraints: blah')
assert 'Self-Correction' not in r and 'Good text' in r, f'3: {r}'

# Test 4: aggressive mode with formal opening
r = strip_cot('noise planning\n\nHadirin yang terhormat, pidato', aggressive=True)
assert 'Hadirin' in r and 'noise' not in r, f'4: {r}'

# Test 5: clean_transcript_content delegates to strip_cot
r = clean_transcript_content('text [THINK]hidden[/THINK] visible')
assert 'hidden' not in r and 'visible' in r, f'5: {r}'

# Test 6: _clean_cot delegates to strip_cot
r = _clean_cot('text <think>hidden</think> visible')
assert 'hidden' not in r and 'visible' in r, f'6: {r}'

# Test 7: JSON leak removal
r = strip_cot('text {"legal_standing": 20} more')
assert 'legal_standing' not in r and 'text' in r and 'more' in r, f'7: {r}'

# Test 8: Empty/None
assert strip_cot('') == '', '8a'
assert strip_cot(None) is None, '8b'

# Test 9: Code blocks removed
r = strip_cot('before\n```json\nsecret\n```\nafter')
assert 'secret' not in r, f'9: {r}'

# Test 10: Non-thinking text preserved
original = 'Permohonan Pemohon dikabulkan. Pasal 28D ayat (1) UUD 1945.'
r = strip_cot(original)
assert r == original, f'10: expected unchanged, got: {r}'

print('All 10 tests PASSED')
