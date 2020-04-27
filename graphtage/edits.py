import itertools
from abc import abstractmethod, ABC
from typing import Any, Callable, cast, Collection, Generic, Iterator, List, Optional, Type, TypeVar

from .printer import Back, Fore, Printer
from .search import IterativeTighteningSearch
from .bounds import Range
from .tree import CompoundEdit, Edit, EditedTreeNode, TreeNode


class AbstractEdit(Edit, ABC):
    def __init__(self,
                 from_node: TreeNode,
                 to_node: TreeNode = None,
                 constant_cost: Optional[int] = 0,
                 cost_upper_bound: Optional[int] = None
    ):
        self.from_node: TreeNode = from_node
        self.to_node: TreeNode = to_node
        self._constant_cost = constant_cost
        self._cost_upper_bound = cost_upper_bound
        self._valid: bool = True
        self.initial_bounds = self.bounds()

    def is_complete(self) -> bool:
        return not self.valid or self.bounds().definitive()

    @property
    def valid(self) -> bool:
        return self._valid

    @valid.setter
    def valid(self, is_valid: bool):
        self._valid = is_valid

    def __lt__(self, other):
        return self.bounds() < other.bounds()

    def bounds(self) -> Range:
        lb = self._constant_cost
        if self._cost_upper_bound is None:
            if self.to_node is None:
                ub = self.initial_bounds.upper_bound
            else:
                ub = self.from_node.total_size + self.to_node.total_size + 1
        else:
            ub = self._cost_upper_bound
        return Range(lb, ub)


class ConstantCostEdit(AbstractEdit, ABC):
    def __init__(
            self,
            from_node: TreeNode,
            to_node: TreeNode = None,
            cost: int = 0
    ):
        super().__init__(
            from_node=from_node,
            to_node=to_node,
            constant_cost=cost,
            cost_upper_bound=cost
        )

    def tighten_bounds(self) -> bool:
        return False


class AbstractCompoundEdit(AbstractEdit, CompoundEdit, ABC):
    @abstractmethod
    def edits(self) -> Iterator[Edit]:
        raise NotImplementedError()

    def print(self, formatter: 'graphtage.formatter.Formatter', printer: Printer):
        for edit in self.edits():
            edit.print(formatter, printer)

    def __iter__(self) -> Iterator[Edit]:
        return self.edits()


class PossibleEdits(AbstractCompoundEdit):
    def __init__(
            self,
            from_node: TreeNode,
            to_node: TreeNode,
            edits: Iterator[Edit] = (),
            initial_cost: Optional[Range] = None
    ):
        if initial_cost is not None:
            self.initial_bounds = initial_cost
        self._search: IterativeTighteningSearch[Edit] = IterativeTighteningSearch(
            possibilities=edits,
            initial_bounds=initial_cost
        )
        while not self._search.bounds().finite:
            self._search.tighten_bounds()
        super().__init__(from_node=from_node, to_node=to_node)

    @property
    def valid(self) -> bool:
        if not super().valid:
            return False
        while self._search.best_match is not None and not self._search.best_match.valid:
            self._search.remove_best()
        is_valid = self._search.best_match is not None
        if not is_valid:
            self.valid = False
        return is_valid

    @valid.setter
    def valid(self, is_valid: bool):
        self._valid = is_valid

    def best_possibility(self) -> Edit:
        return self._search.best_match

    def edits(self) -> Iterator[Edit]:
        best = self.best_possibility()
        if best is not None:
            yield best

    def tighten_bounds(self) -> bool:
        tightened = self._search.tighten_bounds()
        # Calling self.valid checks whether our best match is invalid
        self.valid
        return tightened

    def bounds(self) -> Range:
        return self._search.bounds()


class Match(ConstantCostEdit):
    def __init__(self, match_from: TreeNode, match_to: TreeNode, cost: int):
        super().__init__(
            from_node=match_from,
            to_node=match_to,
            cost=cost
        )

    def on_diff(self, from_node: EditedTreeNode):
        super().on_diff(from_node)
        from_node.matched_to = self.to_node

    def print(self, formatter: 'graphtage.formatter.Formatter', printer: Printer):
        if self.bounds() > Range(0, 0):
            with printer.bright().background(Back.RED).color(Fore.WHITE):
                with printer.strike():
                    formatter.print(printer=printer, node=self.from_node, with_edits=False)
            with printer.color(Fore.CYAN):
                printer.write(' -> ')
            with printer.bright().background(Back.GREEN).color(Fore.WHITE):
                with printer.under_plus():
                    formatter.print(printer=printer, node=self.to_node, with_edits=False)
        else:
            formatter.print(printer=printer, node=self.to_node, with_edits=False)

    def __repr__(self):
        return f"{self.__class__.__name__}(match_from={self.from_node!r}, match_to={self.to_node!r}, cost={self.bounds().lower_bound!r})"


class Replace(ConstantCostEdit):
    def __init__(self, to_replace: TreeNode, replace_with: TreeNode):
        cost = max(to_replace.total_size, replace_with.total_size) + 1
        super().__init__(
            from_node=to_replace,
            to_node=replace_with,
            cost=cost
        )

    def print(self, formatter: 'graphtage.formatter.Formatter', printer: Printer):
        if self.bounds().upper_bound > 0:
            with printer.bright().color(Fore.WHITE).background(Back.RED):
                formatter.print(printer, self.from_node, False)
            with printer.color(Fore.CYAN):
                printer.write(' -> ')
            with printer.bright().color(Fore.WHITE).background(Back.GREEN):
                formatter.print(False, self.to_node, False)
        else:
            formatter.print(self.to_node, printer, False)

    def __repr__(self):
        return f"{self.__class__.__name__}(to_replace={self.from_node!r}, replace_with={self.to_node!r})"


class Remove(ConstantCostEdit):
    def __init__(self, to_remove: TreeNode, remove_from: TreeNode, penalty: int = 1):
        super().__init__(
            from_node=to_remove,
            to_node=remove_from,
            cost=to_remove.total_size + penalty,
        )

    def on_diff(self, from_node: EditedTreeNode):
        super().on_diff(from_node)
        from_node.removed = True

    def print(self, formatter: 'graphtage.formatter.Formatter', printer: Printer):
        with printer.bright():
            with printer.background(Back.RED):
                with printer.color(Fore.WHITE):
                    if not printer.ansi_color:
                        printer.write('~~~~')
                        formatter.print(printer, self.from_node, False)
                        printer.write('~~~~')
                    else:
                        with printer.strike():
                            formatter.print(printer, self.from_node, False)

    def __repr__(self):
        return f"{self.__class__.__name__}({self.from_node!r}, remove_from={self.to_node!r})"


class Insert(ConstantCostEdit):
    def __init__(self, to_insert: TreeNode, insert_into: TreeNode, penalty: int = 1):
        super().__init__(
            from_node=to_insert,
            to_node=insert_into,
            cost=to_insert.total_size + penalty
        )

    def on_diff(self, from_node: EditedTreeNode):
        dest = cast(EditedTreeNode, self.insert_into)
        dest.inserted.append(cast(TreeNode, from_node))

    @property
    def insert_into(self) -> TreeNode:
        return self.to_node

    @property
    def to_insert(self) -> TreeNode:
        return self.from_node

    def print(self, formatter: 'graphtage.formatter.Formatter', printer: Printer):
        with printer.bright().background(Back.GREEN).color(Fore.WHITE):
            if not printer.ansi_color:
                printer.write('++++')
                formatter.print(printer, self.to_insert, False)
                printer.write('++++')
            else:
                with printer.under_plus():
                    formatter.print(printer, self.to_insert, False)

    def __repr__(self):
        return f"{self.__class__.__name__}(to_insert={self.to_insert!r}, insert_into={self.insert_into!r})"


C = TypeVar('C', bound=Collection)


class EditCollection(AbstractCompoundEdit, Generic[C]):
    def __init__(
            self,
            from_node: TreeNode,
            to_node: Optional[TreeNode],
            collection: Type[C],
            add_to_collection: Callable[[C, Edit], Any],
            edits: Iterator[Edit],
            explode_edits: bool = True
    ):
        self._edit_iter: Iterator[Edit] = edits
        self._sub_edits: C[Edit] = collection()
        cost_upper_bound = from_node.total_size + 1
        if to_node is not None:
            cost_upper_bound += to_node.total_size
        self._cost = None
        self.explode_edits = explode_edits
        self._add: Callable[[Edit], Any] = lambda e: add_to_collection(self._sub_edits, e)
        super().__init__(from_node=from_node,
                         to_node=to_node,
                         cost_upper_bound=cost_upper_bound)

    @property
    def valid(self) -> bool:
        if not super().valid:
            return False
        is_valid = True
        if self._edit_iter is None:
            for e in self._sub_edits:
                if not e.valid:
                    is_valid = False
                    break
        if not is_valid:
            self.valid = False
        return is_valid

    @valid.setter
    def valid(self, is_valid: bool):
        self._valid = is_valid

    def print(self, formatter: 'graphtage.formatter.Formatter', printer: Printer):
        for sub_edit in self.edits():
            sub_edit.print(formatter, printer)

    def _expand_edits(self) -> Optional[Edit]:
        if self._edit_iter is not None:
            try:
                next_edit = next(self._edit_iter)
                self._cost = None
                if self.explode_edits and isinstance(next_edit, CompoundEdit):
                    self._edit_iter = itertools.chain(self._edit_iter, next_edit.edits())
                    return self._expand_edits()
                else:
                    self._add(next_edit)
                    return next_edit
            except StopIteration:
                self._edit_iter = None
        return None

    def edits(self) -> Iterator[Edit]:
        yield from iter(self._sub_edits)
        while True:
            next_edit = self._expand_edits()
            if next_edit is None:
                break
            yield next_edit

    def _is_tightened(self, starting_bounds: Range) -> bool:
        return not self.valid or self.bounds().lower_bound > starting_bounds.lower_bound or \
            self.bounds().upper_bound < starting_bounds.upper_bound

    def tighten_bounds(self) -> bool:
        if not self.valid:
            return False
        starting_bounds: Range = self.bounds()
        while True:
            if self._expand_edits() and self._is_tightened(starting_bounds):
                return True
            tightened = False
            for child in self._sub_edits:
                if child.tighten_bounds():
                    self._cost = None
                    if not child.valid:
                        self.valid = False
                        return True
                    tightened = True
                    new_cost = self.bounds()
                    # assert new_cost.lower_bound >= starting_bounds.lower_bound
                    # assert new_cost.upper_bound <= starting_bounds.upper_bound
                    if new_cost.lower_bound > starting_bounds.lower_bound or \
                            new_cost.upper_bound < starting_bounds.upper_bound:
                        return True
                else:
                    assert not child.valid or child.bounds().definitive()
            if not tightened and self._edit_iter is None:
                return self._is_tightened(starting_bounds)

    def bounds(self) -> Range:
        if not self.valid:
            self._cost = Range()
        if self._cost is not None:
            return self._cost
        elif self._edit_iter is None:
            # We've expanded all of the sub-edits, so calculate the bounds explicitly:
            total_cost = sum(e.bounds() for e in self._sub_edits)
        else:
            # We have not yet expanded all of the sub-edits
            total_cost = Range(0, self._cost_upper_bound)
            for e in self._sub_edits:
                total_cost.lower_bound += e.bounds().lower_bound
                total_cost.upper_bound -= e.initial_bounds.upper_bound - e.bounds().upper_bound
        if total_cost.lower_bound > super().bounds().upper_bound:
            self.valid = False
            return Range()
        total_cost.upper_bound = min(super().bounds().upper_bound, total_cost.upper_bound)
        if self._edit_iter is None and total_cost.definitive():
            self._cost = total_cost
        return total_cost

    def __len__(self):
        return sum(1 for _ in self.edits())

    def __repr__(self):
        return f"{self.__class__.__name__}(*{self._sub_edits!r})"


class EditSequence(EditCollection[List]):
    def __init__(
            self,
            from_node: TreeNode,
            to_node: Optional[TreeNode],
            edits: Iterator[Edit],
            explode_edits: bool = True
    ):
        super().__init__(
            from_node=from_node,
            to_node=to_node,
            collection=list,
            add_to_collection=list.append,
            edits=edits
        )
