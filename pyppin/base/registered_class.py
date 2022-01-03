"""Make it easy to look up subclasses of an abstract class by name."""
from typing import Any, Dict, Optional, Tuple, Type


class RegisteredClass(type):
    """A metaclass to make classes findable through a registry.

    RegisteredClass is a metaclass that lets you define classes whose subclasses you can look up
    by name. This is useful if (for example) you want to define an abstract class in a library,
    have users of the library define their own implementations of that class, and pick which
    implementation you want to use at runtime based on a parameter. For example::

       class AbstractWorker(metaclass=RegisteredClass):
           ... define some stuff ...

           @classmethod
           def make(cls, worker: str, other_arguments) -> "AbstractWorker":
               return RegisteredClass.get(AbstractWorker, worker)(other_arguments)

       # In another file
       class RealWorker(AbstractWorker):
           ... just a normal subclass ...

    You access this registration using two static methods:

    * ``RegisteredClass.get(superclass, name)`` returns a named subclass of the superclass
    * ``RegisteredClass.subclasses(superclass)`` returns all registered subclasses of that class.

    Or via class methods:

    * ``AbstractWorker.get_subclass(name)  # type: ignore``
    * ``AbstractWorker.subclasses()  # type: ignore``

    You can also define "intermediate" classes which don't themselves appear in the registry. For
    example::

        class RemoteWorker(AbstractWorker, register=False):  # type: ignore
            ... some partial implementation of AbstractWorker ...

        class RealRemoteWorker(RemoteWorker):
            ... a concrete worker ...

    Then ``RegisteredClass.subclasses(AbstractWorker)`` will return `RealWorker` and
    `RealRemoteWorker` (but not `RemoteWorker`), and ``RegisteredClass.subclasses(RemoteWorker)``
    will return `RealRemoteWorker`.

    Every subclass must be registered with a unique name, which by default is just the name of the
    class. You can override this with ``registration_name="Foo"``.


    MYPY WARNING: There are some bugs in the way mypy handles dynamic type declarations. As a
    result, if you use any of the class methods (rather than ``RegistrationClass.*``) or if you
    pass any arguments like `register` or `registration_name`, you have to mark the line as
    ``# type: ignore``.  Sorry.
    """

    # Type signature to make mypy happy: All types that use this as a metaclass will have this
    # as a class variable.
    _registry: Dict[str, "RegisteredClass"]

    @staticmethod
    def get(superclass: "RegisteredClass", name: str) -> "RegisteredClass":
        """Get a named subclass of superclass.

        Args:
          superclass: A class whose metaclass is RegisteredClass.
          name: The name under which a subclass was registered -- usually the name of the class,
            unless you've set registration_name in its class declaration.
        """
        assert hasattr(superclass, "_registry")
        if name not in superclass._registry:
            raise KeyError(
                f'No subclass "{name}" of "{superclass.__name__}" has been registered.'
            )
        result = superclass._registry[name]
        assert issubclass(result, superclass)
        return result

    @staticmethod
    def subclasses(superclass: "RegisteredClass") -> Dict[str, "RegisteredClass"]:
        """Return all the subclasses of a given registered class."""
        if not hasattr(superclass, "_registry"):
            raise TypeError(f"The class {superclass} is not a registered class.")
        # This comprehension serves two purposes. First, it means we don't hand the caller a mutable
        # pointer into the real registry, which could cause all hell to break loose. Second, it
        # means that if the caller passes a *subclass* of a registered class -- e.g., a partial
        # implementation -- we correctly return its subclasses!
        return {
            name: class_
            for name, class_ in superclass._registry.items()
            if issubclass(class_, superclass) and class_ != superclass
        }

    def __new__(
        metaclass,
        name: str,
        bases: Tuple[Type],
        namespace: Dict[str, Any],
        register: bool = True,
        registration_name: Optional[str] = None,
    ) -> Any:
        # This function gets called when a new registered class (ie one whose metaclass is
        # RegisteredClass) is declared. We set up its registry and its subclass initializer.
        class_ = type(name, bases, namespace)

        def init_subclass(
            cls: type, register: bool = True, registration_name: Optional[str] = None
        ) -> None:
            if register:
                registration_name = registration_name or cls.__name__
                # Don't register the root class itself, that's pretty much never useful.
                if registration_name == name:
                    return
                if registration_name in cls._registry:  # type: ignore
                    raise ValueError(
                        f"There is already a registered subclass of {name} named "
                        f"{registration_name}"
                    )
                cls._registry[registration_name] = cls  # type: ignore

        # Doing it this way makes mypy happier.
        registry: Dict[str, Type[class_]] = {}  # type: ignore
        setattr(class_, "_registry", registry)
        setattr(class_, "__init_subclass__", classmethod(init_subclass))

        # Also define some class implementations of the static functions. Alas, using these makes
        # mypy freak out, so if you do use them, you'll have to mark it # type: ignore.

        def get_subclass(superclass: "RegisteredClass", name: str) -> "RegisteredClass":
            return RegisteredClass.get(superclass, name)

        def subclasses(superclass: "RegisteredClass") -> Dict[str, "RegisteredClass"]:
            return RegisteredClass.subclasses(superclass)

        setattr(class_, "get_subclass", classmethod(get_subclass))
        setattr(class_, "subclasses", classmethod(subclasses))

        return class_
