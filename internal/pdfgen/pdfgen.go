package pdfgen

import (
	"fmt"
	"os"
	"regexp"
	"strings"
	"time"

	"github.com/jung-kurt/gofpdf"
)

type PDFGenerator struct {
	pdf *gofpdf.Fpdf
}

func New() *PDFGenerator {
	pdf := gofpdf.New("P", "mm", "A4", "")
	pdf.SetAutoPageBreak(true, 15)

	return &PDFGenerator{
		pdf: pdf,
	}
}

func (g *PDFGenerator) GenerateReport(clusterName, analysis string, outputPath string) error {
	g.pdf.AddPage()

	g.addHeader(clusterName)
	g.pdf.Ln(3)
	g.addTimestamp()
	g.pdf.Ln(6)

	g.addContent(analysis)

	g.addFooter()

	return g.pdf.OutputFileAndClose(outputPath)
}

func (g *PDFGenerator) addHeader(clusterName string) {
	// Helmcode brand colors
	// Purple: #6C62FF (RGB: 108, 98, 255)
	// Background light: #F8FAFF (RGB: 248, 250, 255)
	// Dark text: #1A1A1A (RGB: 26, 26, 26)

	// Add background banner with brand color
	g.pdf.SetFillColor(108, 98, 255) // Purple
	g.pdf.Rect(0, 0, 210, 45, "F")

	g.pdf.Ln(8)
	g.pdf.SetFont("Arial", "B", 24)
	g.pdf.SetTextColor(255, 255, 255) // White text on purple
	g.pdf.CellFormat(0, 12, "Kubernetes Health Report", "", 1, "C", false, 0, "")

	g.pdf.SetFont("Arial", "", 12)
	g.pdf.SetTextColor(255, 255, 255)
	g.pdf.CellFormat(0, 10, fmt.Sprintf("Cluster: %s", clusterName), "", 1, "C", false, 0, "")
}

func (g *PDFGenerator) addTimestamp() {
	timestamp := time.Now().Format("Monday, January 2, 2006 at 15:04 MST")
	g.pdf.SetFont("Arial", "I", 9)
	g.pdf.SetTextColor(120, 120, 120)
	g.pdf.CellFormat(0, 6, fmt.Sprintf("Generated: %s", timestamp), "", 1, "C", false, 0, "")
}

func (g *PDFGenerator) addContent(analysis string) {
	lines := strings.Split(analysis, "\n")

	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			g.pdf.Ln(3)
			continue
		}

		if strings.HasPrefix(line, "# ") {
			g.addH1(strings.TrimPrefix(line, "# "))
		} else if strings.HasPrefix(line, "## ") {
			g.addH2(strings.TrimPrefix(line, "## "))
		} else if strings.HasPrefix(line, "### ") {
			g.addH3(strings.TrimPrefix(line, "### "))
		} else if strings.HasPrefix(line, "- ") {
			g.addBullet(strings.TrimPrefix(line, "- "))
		} else if matched, _ := regexp.MatchString(`^\d+\.`, line); matched {
			g.addNumberedItem(line)
		} else if strings.HasPrefix(line, ">") {
			g.addQuote(strings.TrimPrefix(line, "> "))
		} else if strings.HasPrefix(line, "---") {
			g.addDivider()
		} else {
			g.addParagraph(line)
		}
	}
}

func (g *PDFGenerator) addH1(text string) {
	g.pdf.Ln(5)

	// Add colored background bar for H1
	g.pdf.SetFillColor(240, 245, 255) // Light blue background
	currentY := g.pdf.GetY()
	g.pdf.Rect(10, currentY, 190, 10, "F")

	g.pdf.SetFont("Arial", "B", 16)
	g.pdf.SetTextColor(0, 51, 102)

	text = g.cleanMarkdown(text)
	g.pdf.MultiCell(0, 10, text, "", "L", false)
	g.pdf.Ln(3)
}

func (g *PDFGenerator) addH2(text string) {
	g.pdf.Ln(4)

	// Add left border accent
	currentY := g.pdf.GetY()
	g.pdf.SetFillColor(108, 98, 255) // Purple accent
	g.pdf.Rect(10, currentY, 3, 7, "F")

	g.pdf.SetX(15)
	g.pdf.SetFont("Arial", "B", 13)
	g.pdf.SetTextColor(0, 51, 102)

	text = g.cleanMarkdown(text)
	g.pdf.MultiCell(0, 7, text, "", "L", false)
	g.pdf.Ln(2)
}

func (g *PDFGenerator) addH3(text string) {
	g.pdf.Ln(3)

	// Add a subtle left border for H3
	currentY := g.pdf.GetY()
	g.pdf.SetDrawColor(200, 200, 200)
	g.pdf.Line(10, currentY, 10, currentY+6)

	g.pdf.SetX(12)
	g.pdf.SetFont("Arial", "B", 11)
	g.pdf.SetTextColor(40, 40, 40)

	text = g.cleanMarkdown(text)
	g.pdf.MultiCell(0, 6, text, "", "L", false)
	g.pdf.Ln(1)
}

func (g *PDFGenerator) addBullet(text string) {
	currentY := g.pdf.GetY()

	// Draw a colored bullet point
	g.pdf.SetFillColor(108, 98, 255) // Purple
	g.pdf.Circle(13, currentY+2, 1, "F")

	g.pdf.SetX(16)
	g.pdf.SetFont("Arial", "", 10)
	g.pdf.SetTextColor(60, 60, 60)

	text = g.cleanMarkdown(text)
	g.pdf.MultiCell(0, 5, text, "", "L", false)
}

func (g *PDFGenerator) addNumberedItem(text string) {
	g.pdf.Ln(2)

	// Extract number if present
	text = g.cleanMarkdown(text)

	// Add light background for numbered items
	currentY := g.pdf.GetY()
	g.pdf.SetFillColor(250, 250, 252)
	g.pdf.Rect(10, currentY, 190, 6, "F")

	g.pdf.SetFont("Arial", "B", 10)
	g.pdf.SetTextColor(40, 40, 40)
	g.pdf.MultiCell(0, 6, text, "", "L", false)
	g.pdf.Ln(1)
}

func (g *PDFGenerator) addQuote(text string) {
	g.pdf.Ln(2)

	currentY := g.pdf.GetY()

	// Draw a colored left border for emphasis
	g.pdf.SetFillColor(108, 98, 255) // Purple
	g.pdf.Rect(15, currentY, 2, 8, "F")

	// Light background box
	g.pdf.SetFillColor(248, 247, 255) // Very light purple
	g.pdf.Rect(17, currentY, 178, 8, "F")

	g.pdf.SetX(20)
	g.pdf.SetFont("Arial", "I", 10)
	g.pdf.SetTextColor(60, 60, 100)

	text = g.cleanMarkdown(text)
	g.pdf.MultiCell(0, 4, text, "", "L", false)
	g.pdf.Ln(2)
}

func (g *PDFGenerator) addParagraph(text string) {
	g.pdf.SetFont("Arial", "", 10)
	g.pdf.SetTextColor(60, 60, 60)

	text = g.cleanMarkdown(text)
	g.pdf.MultiCell(0, 5, text, "", "L", false)
}

func (g *PDFGenerator) addDivider() {
	g.pdf.Ln(3)
	currentY := g.pdf.GetY()

	// Draw a gradient-like divider with multiple lines
	g.pdf.SetDrawColor(108, 98, 255)
	g.pdf.SetLineWidth(0.5)
	g.pdf.Line(15, currentY, 195, currentY)

	g.pdf.SetDrawColor(200, 200, 220)
	g.pdf.SetLineWidth(0.2)
	g.pdf.Line(15, currentY+0.5, 195, currentY+0.5)

	g.pdf.SetLineWidth(0.2) // Reset to default
	g.pdf.Ln(3)
}

func (g *PDFGenerator) addFooter() {
	g.pdf.SetY(-20)
	g.pdf.SetFont("Arial", "I", 8)
	g.pdf.SetTextColor(150, 150, 150)
	g.pdf.CellFormat(0, 10, "Generated by K8s Observer powered by Claude AI", "", 0, "C", false, 0, "")
	g.pdf.Ln(4)
	g.pdf.CellFormat(0, 10, fmt.Sprintf("Page %d", g.pdf.PageNo()), "", 0, "C", false, 0, "")
}

func (g *PDFGenerator) cleanMarkdown(text string) string {
	// Replace important emojis with visual ASCII symbols
	emojiReplacements := map[string]string{
		"\U0001F534": " [!] ",     // Red circle -> Critical marker
		"\U0001F7E0": " [*] ",     // Orange circle -> Warning marker
		"\U0001F7E2": " [+] ",     // Green circle -> OK marker
		"\U0001F4CA": "",          // Bar chart - remove
		"\U0001F4C8": " ^ ",       // Chart increasing
		"\U0001F4C9": " v ",       // Chart decreasing
		"\U00002705": " [OK] ",    // Check mark
		"\U0000274C": " [X] ",     // Cross mark
		"\U000026A0": " [!] ",     // Warning sign
		"\U0001F6A8": " [!!] ",    // Police car light
		"\U0001F4A1": " (*) ",     // Light bulb
		"\U0001F4DD": " - ",       // Memo
		"\U0001F527": " [T] ",     // Wrench (tool)
		"\U0001F4E6": " [#] ",     // Package
	}

	for emoji, replacement := range emojiReplacements {
		text = strings.ReplaceAll(text, emoji, replacement)
	}

	// Remove remaining emojis but keep common symbols
	emojiRegex := regexp.MustCompile(`[\x{1F300}-\x{1F9FF}]|[\x{1F100}-\x{1F64F}]|[\x{1F680}-\x{1F6FF}]`)
	text = emojiRegex.ReplaceAllString(text, "")

	// Clean markdown formatting
	boldRegex := regexp.MustCompile(`\*\*([^*]+)\*\*`)
	text = boldRegex.ReplaceAllString(text, "$1")

	italicRegex := regexp.MustCompile(`\*([^*]+)\*`)
	text = italicRegex.ReplaceAllString(text, "$1")

	codeRegex := regexp.MustCompile("`([^`]+)`")
	text = codeRegex.ReplaceAllString(text, "$1")

	linkRegex := regexp.MustCompile(`\[([^\]]+)\]\([^)]+\)`)
	text = linkRegex.ReplaceAllString(text, "$1")

	// Replace accented characters with their base forms (for better PDF compatibility)
	accentReplacements := map[string]string{
		"á": "a", "Á": "A", "à": "a", "À": "A", "â": "a", "Â": "A", "ä": "a", "Ä": "A",
		"é": "e", "É": "E", "è": "e", "È": "E", "ê": "e", "Ê": "E", "ë": "e", "Ë": "E",
		"í": "i", "Í": "I", "ì": "i", "Ì": "I", "î": "i", "Î": "I", "ï": "i", "Ï": "I",
		"ó": "o", "Ó": "O", "ò": "o", "Ò": "O", "ô": "o", "Ô": "O", "ö": "o", "Ö": "O",
		"ú": "u", "Ú": "U", "ù": "u", "Ù": "U", "û": "u", "Û": "U", "ü": "u", "Ü": "U",
		"ñ": "n", "Ñ": "N",
		"ç": "c", "Ç": "C",
	}

	for accented, plain := range accentReplacements {
		text = strings.ReplaceAll(text, accented, plain)
	}

	// Replace common problematic characters
	replacements := map[string]string{
		"\u2022": "-",   // bullet
		"\u2013": "-",   // en dash
		"\u2014": "-",   // em dash
		"\u2018": "'",   // left single quote
		"\u2019": "'",   // right single quote
		"\u201C": "\"",  // left double quote
		"\u201D": "\"",  // right double quote
		"\u2026": "...", // ellipsis
	}

	for old, new := range replacements {
		text = strings.ReplaceAll(text, old, new)
	}

	return text
}

func GenerateReportPDF(clusterName, analysis, outputPath string) error {
	gen := New()
	return gen.GenerateReport(clusterName, analysis, outputPath)
}

func GenerateTempReportPDF(clusterName, analysis string) (string, error) {
	tempFile, err := os.CreateTemp("", "k8s-report-*.pdf")
	if err != nil {
		return "", fmt.Errorf("failed to create temp file: %w", err)
	}
	tempFile.Close()

	if err := GenerateReportPDF(clusterName, analysis, tempFile.Name()); err != nil {
		os.Remove(tempFile.Name())
		return "", err
	}

	return tempFile.Name(), nil
}
