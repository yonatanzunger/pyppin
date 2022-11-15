from typing import Dict, Hashable, Iterator, List, Optional, Set, Tuple, TypeVar, Union

K = TypeVar('K', bound=Hashable)
V = TypeVar('V')


class OverlayDict(Dict[K, V]):
    def __init__(self, *dicts: Dict[K, V]) -> None:
        self.layers: List[Dict[K, V]] = list(dicts)

    def push(self, layer: Union[Dict[K, V], 'OverlayDict[K, V]']) -> None:
        if isinstance(layer, OverlayDict):
            self.layers.extend(layer.layers)
        else:
            self.layers.append(layer)

    def pop(self) -> Optional[Dict[K, V]]:
        return self.layers.pop() if self.layers else None

    def __len__(self) -> int:
        return len(set().union(self.layers))

    def __length_hint__(self) -> int:
        return max(len(layer) for layer in self.layers)

    def __getitem__(self, key: K) -> V:
        for layer in reversed(self.layers):
            if key in layer:
                return layer[key]
        raise KeyError('Key not found')

    def __setitem__(self, key: K) -> V:
        raise NotImplementedError(
            "OverlayDicts are read-only; mutate the layers directly if needed"
        )

    def __delitem__(self, key: K) -> None:
        raise NotImplementedError(
            "OverlayDicts are read-only; mutate the layers directly if needed"
        )

    def __iter__(self) -> Iterator[K]:
        yield from self.keys()

    def __contains__(self, key: K) -> bool:
        return any(key in layer for layer in self.layers)

    def list(self) -> List[K]:
        return list(iter(self))

    def clear(self) -> None:
        self.layers.clear()

    def flatten(self) -> None:
        return dict(self.items())

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        try:
            return self[key]
        except KeyError:
            return default

    def items(self) -> Iterator[Tuple[K, V]]:
        keys: Set[K] = set()
        for layer in reversed(self.layers):
            for k, v in layer.items():
                if k not in keys:
                    yield k, v
                    keys.add(k)

    def keys(self) -> Iterator[K]:
        yield from set().union(self.layers)

    def values(self) -> Iterator[V]:
        for k, v in self.items():
            yield v
