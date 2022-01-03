import unittest

from pyppin.base.registered_class import RegisteredClass


class AbstractClass(metaclass=RegisteredClass):
    """This is our fake abstract superclass."""

    pass


class ConcreteSubclass1(AbstractClass):
    """Here's a concrete implementation."""

    pass


class ConcreteSubclass2(AbstractClass, registration_name="Foo"):  # type: ignore
    """Here's another concrete implementation, with a custom name."""

    pass


class IntermediateClass(AbstractClass, register=False):  # type: ignore
    """Here's a semi-abstract subclass. We don't want it to be something you can look up in the
    registration list, but its subclasses should be available.
    """

    pass


class DeepConcreteSubclass(IntermediateClass):
    """Here's a subclass of the intermediate class, which should be available."""

    pass


class RegistrationTest(unittest.TestCase):
    def testSubclasses(self) -> None:
        # Check that the overall list makes sense
        self.assertEqual(
            {
                "ConcreteSubclass1": ConcreteSubclass1,
                "DeepConcreteSubclass": DeepConcreteSubclass,
                "Foo": ConcreteSubclass2,
            },
            RegisteredClass.subclasses(AbstractClass),
        )

        self.assertEqual(
            {"DeepConcreteSubclass": DeepConcreteSubclass},
            RegisteredClass.subclasses(IntermediateClass),
        )

        self.assertEqual({}, RegisteredClass.subclasses(ConcreteSubclass1))

    def testGetByName(self) -> None:
        self.assertEqual(
            ConcreteSubclass1, RegisteredClass.get(AbstractClass, "ConcreteSubclass1")
        )
        self.assertEqual(ConcreteSubclass2, RegisteredClass.get(AbstractClass, "Foo"))
        # Shouldn't work, this class got a custom name.
        with self.assertRaises(KeyError):
            RegisteredClass.get(AbstractClass, "ConcreteSubclass2")

        # This one shouldn't be in the list at all.
        with self.assertRaises(KeyError):
            RegisteredClass.get(AbstractClass, "IntermediateClass")

        # But this one should work fine.
        self.assertEqual(
            DeepConcreteSubclass,
            RegisteredClass.get(AbstractClass, "DeepConcreteSubclass"),
        )

    def testReplaceFails(self) -> None:
        with self.assertRaises(ValueError):

            class BadConcreteSubclass(AbstractClass, registration_name="Foo"):  # type: ignore
                pass

    def testClassMethods(self) -> None:
        self.assertEqual(
            ConcreteSubclass1, AbstractClass.get_subclass("ConcreteSubclass1")  # type: ignore
        )
        self.assertEqual(
            {
                "ConcreteSubclass1": ConcreteSubclass1,
                "DeepConcreteSubclass": DeepConcreteSubclass,
                "Foo": ConcreteSubclass2,
            },
            AbstractClass.subclasses(),  # type: ignore
        )
        self.assertEqual(
            {"DeepConcreteSubclass": DeepConcreteSubclass},
            IntermediateClass.subclasses(),  # type: ignore
        )


if __name__ == "__main__":
    unittest.main()
