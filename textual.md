# Evaluating the Benefits of Using the Textual Library

I have taken some time to investigate the potential of moving Spydertop from Asciimatics, our current UI library, to Textual. The update would require some time and effort, but offers substantial benefits such as simplifying existing code and making Spydertop easier to maintain in the future. Despite the library being relatively new and lacking some documentation, it is still comparable to the version currently in use. I would recommended to put further work into moving over to the new library, and to start with ensuring that Textual would be able to support all of the current elements of Spydertop.

## A Summary of Textual

Textual is a newly released terminal UI library created by [Textualize](https://textualize.io). It provides React-like functionality for creating UI elements, and support for CSS styling. It includes a terminal tool to run a development version of the app with live reloading of the CSS and a developer console. Our current UI library, Asciimatics, lacks most of these features. More information on Textual can be found [here](https://textual.textualize.io/).

## Benefits of Textual

Moving to Textual would make the implementation of the Spydertop UI easier to maintain. It would use a structure similar to React and allows the use of CSS, making it easy for someone not familiar with Spydertop to make minor changes. In addition, Spydertop currently contains multiple classes which are duplications of Asciimatics code with some small changes to allow for features not present in the library. These would no longer be necessary with Textual. Finally, Textual has first-class support for typing, allowing better integrating with our current linting tools (`pylint` and `pyright`).

## Disadvantages of Moving to Textual

The current implementation of Spydertop makes heavy use of Asciimatics, and would require a full rewrite of the UI code to use Textual. Luckily, very little of the business logic needs to change, and it would provide the opportunity to refactor the UI. However, this change would require some time to complete, and it would be difficult to use a gradual transition due to the nature of Textual and Asciimatics.

In summary, I would recommend continuing to work on migrating to Textual on a separate git branch. First, I would aim to migrate some of the most critical UI elements to ensure the work with Textual. If we determine that this change would be best for Spydertop, I would slowly migrate the rest of the UI in parallel to the normal development of Spydertop.