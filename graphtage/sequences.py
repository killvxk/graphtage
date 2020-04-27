from abc import abstractmethod, ABC
from typing import Any, Callable, cast, Iterable, Optional, Sized, Union, List

from .edits import AbstractCompoundEdit, Insert, Match, Remove
from .formatter import Formatter
from .printer import Printer
from .tree import ContainerNode, Edit, EditedTreeNode


class SequenceEdit(AbstractCompoundEdit, ABC):
    def __init__(
            self,
            from_node,
            *args,
            **kwargs
    ):
        if not isinstance(from_node, SequenceNode):
            raise ValueError(f"from_node must be a SequenceNode, but {from_node!r} is {type(from_node)}!")
        super().__init__(from_node=from_node, *args, **kwargs)

    @property
    def sequence(self) -> 'SequenceNode':
        return cast(SequenceNode, self.from_node)

    def print(self, formatter: Formatter, printer: Printer):
        formatter.get_formatter(self.sequence)(printer, self.sequence, self)


class SequenceNode(ContainerNode, Iterable, Sized, ABC):
    def make_edited(self) -> Union[EditedTreeNode, 'SequenceNode']:
        return self.edited_type()([n.make_edited() for n in self])

    def print(self, printer: Printer):
        SequenceFormatter('[', ']', ',').print(printer, self)


class SequenceFormatter(Formatter):
    def __init__(
            self,
            start_symbol: str,
            end_symbol: str,
            delimiter: str,
            delimiter_callback: Optional[Callable[[Printer], Any]] = None
    ):
        self.start_symbol = start_symbol
        self.end_symbol = end_symbol
        self.delimiter = delimiter
        if delimiter_callback is None:
            self.delimiter_callback: Callable[[Printer], Any] = lambda p: p.write(delimiter)
        else:
            self.delimiter_callback: Callable[[Printer], Any] = delimiter_callback

    def item_newline(self, printer: Printer, is_first: bool = False, is_last: bool = False):
        printer.newline()

    def print_SequenceNode(self, printer: Printer, node: SequenceNode, sequence_edit: Optional[SequenceEdit] = None):
        with printer.bright():
            printer.write(self.start_symbol)
        with printer.indent() as p:
            to_remove: int = 0
            to_insert: int = 0
            if sequence_edit is not None:
                edits: List[Edit] = sequence_edit.edits()
            elif isinstance(node, EditedTreeNode):
                edits: List[Edit] = node.edit.edits()
            else:
                edits: List[Edit] = [Match(child, child, 0) for child in node]
            for i, edit in enumerate(edits):
                if isinstance(edit, Remove):
                    to_remove += 1
                elif isinstance(edit, Insert):
                    to_insert += 1
                while to_remove > 0 and to_insert > 0:
                    to_remove -= 1
                    to_insert -= 1
                if i > 0:
                    with printer.bright():
                        if to_remove:
                            to_remove -= 1
                            with p.strike():
                                self.delimiter_callback(p)
                        elif to_insert:
                            to_insert -= 1
                            with p.under_plus():
                                self.delimiter_callback(p)
                        else:
                            self.delimiter_callback(p)
                self.item_newline(printer, is_first=i == 0)
                edit.print(self, p)
        if len(node) > 0:
            self.item_newline(printer, is_last=True)
        with printer.bright():
            printer.write(self.end_symbol)
