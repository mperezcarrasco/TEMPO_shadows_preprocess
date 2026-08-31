# Minimal Makefile for the DARCLOS-TEMPO paper.
#
#   make           # build paper.pdf
#   make clean     # remove all build artefacts except the PDF
#   make distclean # remove the PDF as well
#   make watch     # rebuild on every save (needs latexmk)

TEX = paper
BIB = references

LATEX  ?= pdflatex
BIBTEX ?= bibtex

.PHONY: all clean distclean watch

all: $(TEX).pdf

$(TEX).pdf: $(TEX).tex $(BIB).bib
	$(LATEX) -interaction=nonstopmode $(TEX).tex
	$(BIBTEX) $(TEX)
	$(LATEX) -interaction=nonstopmode $(TEX).tex
	$(LATEX) -interaction=nonstopmode $(TEX).tex

watch:
	latexmk -pdf -pvc -interaction=nonstopmode $(TEX).tex

clean:
	rm -f $(TEX).aux $(TEX).log $(TEX).out $(TEX).bbl $(TEX).blg \
	      $(TEX).toc $(TEX).lof $(TEX).lot $(TEX).fls $(TEX).fdb_latexmk \
	      $(TEX).synctex.gz

distclean: clean
	rm -f $(TEX).pdf
