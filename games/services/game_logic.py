import random
import uuid
import hashlib

def generate_winning_numbers(guess_min, guess_max, number_of_winners):
    """
    Generate unique winning numbers with transparency (salt + hash).
    """
    if number_of_winners > (guess_max - guess_min + 1):
        raise ValueError("Number of winners exceeds available range.")

    # 1. Generate unique winning numbers
    winning_numbers = random.sample(
        range(guess_min, guess_max + 1),
        number_of_winners
    )

    # 2. Generate random salt
    salt = str(uuid.uuid4())

    # 3. Create hash for transparency
    raw_string = "-".join(map(str, winning_numbers)) + "-" + salt
    hash_value = hashlib.sha256(raw_string.encode()).hexdigest()

    return winning_numbers, salt, hash_value


numbers, salt, hash_val = generate_winning_numbers(1, 100, 3)
print("Winning Numbers (hidden):", numbers)
print("Salt:", salt)
print("Hash:", hash_val)