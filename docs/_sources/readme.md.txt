# pyppin: A toolkit of Python basics

pyppin is a library of "basic components" that can be used in a wide range of contexts -- things
that could hypothetically live in a standard library, only there's no particular reason to put them
in there. It is essentially a box of tools that are slightly less common than the basics, but are
nonetheless damned useful in practice. If the main argument against adding something to the standard
library is "why does it need to be in there, as opposed to elsewhere?" and it's not big enough to
merit its own standalone package, this is a perfectly reasonable place to put it.

The current catalogue is:

## Debugging Tools

- `interact` lets you pop open a REPL at any point in your code, with access to all the local and
    global variables, so you can easily do interactive debugging.

## Better class definition

- `@cache` and `@cachemethod` are decorators that allow fancier (but still one-line) caching of
    function and method results.
- `@lazyinit` lets you defer expensive variable initializations like server connnections until and
    unless you need them.
- `RegisteredClass` lets you automatically register, iterate over, and fetch by name all subclasses
    of an abstract class you define.

## Iteration

- `zipper` flexibly merges multiple sorted iterators into a single, efficient, parallel iterator.

## Scanning directories

- `list_files` lets you list all files recursively in a given directory, managing all the subtle
    corner cases for you.
- `bulk_import` lets you (recursively or not) import all the Python files in a given directory,
    which is especially useful with registered classes.
