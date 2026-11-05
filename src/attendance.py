"""Recognition confirmation before a database write."""


class Confirmation:
    def __init__(self, required: int):
        self.required = required
        self.person = None
        self.frames = 0

    def observe(self, student_id: str | None) -> bool:
        """Return True once on the Nth consecutive matching processed frame."""
        if student_id is None:
            self.person, self.frames = None, 0
            return False
        if student_id != self.person:
            self.person, self.frames = student_id, 0
        self.frames += 1
        return self.frames == self.required
