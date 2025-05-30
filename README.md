# EbookLib-autoupdate

This is a fork of the popular Ebooklib library that aims to keep a package updated with changes from the original codebase. Any changes to [https://github.com/aerkalov/ebooklib] are merged into this package on a weekly basis.

## About EbookLib

EbookLib is a Python library for managing EPUB2/EPUB3 files. It's capable of reading and writing EPUB files programmatically.

We are working on [refreshing the project](https://github.com/aerkalov/ebooklib/issues/318) so please check and comment if you have your own ideas what needs to happen with the project.

The API is designed to be as simple as possible, while at the same time making complex things possible too.  It has support for covers, table of contents, spine, guide, metadata and etc.

EbookLib is used in [Booktype](https://github.com/sourcefabric/Booktype/) from Sourcefabric, as well as [sprits-it!](https://github.com/the-happy-hippo/sprits-it), [fanfiction2ebook](https://github.com/ltouroumov/fanfiction2ebook), [viserlalune](https://github.com/vjousse/viserlalune) and [Telemeta](https://github.com/Parisson/Telemeta).

Packages of EbookLib for GNU/Linux are available in [Debian](https://packages.debian.org/python-ebooklib) and [Ubuntu](http://packages.ubuntu.com/python-ebooklib).

Sphinx documentation is generated from the templates in the docs/ directory and made available at <http://ebooklib.readthedocs.io>

## Usage

### Reading

```py
import ebooklib
from ebooklib import epub

book = epub.read_epub('test.epub')

for image in book.get_items_of_type(ebooklib.ITEM_IMAGE):
    print(image)
```

### Writing

```py
from ebooklib import epub

book = epub.EpubBook()

# set metadata
book.set_identifier("id123456")
book.set_title("Sample book")
book.set_language("en")

book.add_author("Author Authorowski")
book.add_author(
    "Danko Bananko",
    file_as="Gospodin Danko Bananko",
    role="ill",
    uid="coauthor",
)

# create chapter
c1 = epub.EpubHtml(title="Intro", file_name="chap_01.xhtml", lang="hr")
c1.content = (
    "<h1>Intro heading</h1>"
    "<p>Zaba je skocila u baru.</p>"
    '<p><img alt="[ebook logo]" src="static/ebooklib.gif"/><br/></p>'
)

# create image from the local image
image_content = open("ebooklib.gif", "rb").read()
img = epub.EpubImage(
    uid="image_1",
    file_name="static/ebooklib.gif",
    media_type="image/gif",
    content=image_content,
)

# add chapter
book.add_item(c1)
# add image
book.add_item(img)

# define Table Of Contents
book.toc = (
    epub.Link("chap_01.xhtml", "Introduction", "intro"),
    (epub.Section("Simple book"), (c1,)),
)

# add default NCX and Nav file
book.add_item(epub.EpubNcx())
book.add_item(epub.EpubNav())

# define CSS style
style = "BODY {color: white;}"
nav_css = epub.EpubItem(
    uid="style_nav",
    file_name="style/nav.css",
    media_type="text/css",
    content=style,
)

# add CSS file
book.add_item(nav_css)

# basic spine
book.spine = ["nav", c1]

# write to the file
epub.write_epub("test.epub", book, {})
```

## License

EbookLib is licensed under the [AGPL license](LICENSE.txt).

## Authors

Full list of authors is in [AUTHORS.txt](AUTHORS.txt) file.
