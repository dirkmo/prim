class CompileError(ValueError):
    """A user-input error with a source location or token-stream offset."""

    def __init__(self, message, filename=None, line=None, column=None, offset=None):
        self.message = message
        self.filename = filename
        self.line = line
        self.column = column
        self.offset = offset
        location = str(filename) if filename is not None else ''
        if line is not None:
            location += f':{line}'
            if column is not None:
                location += f':{column}'
        if offset is not None:
            location += f':token[{offset}]' if location else f'token[{offset}]'
        super().__init__(f'{location}: {message}' if location else message)
