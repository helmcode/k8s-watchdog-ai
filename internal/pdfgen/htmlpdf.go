package pdfgen

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/chromedp/cdproto/page"
	"github.com/chromedp/chromedp"
)

// GenerateHTMLReportPDF generates a PDF from HTML content using chromedp
func GenerateHTMLReportPDF(clusterName, htmlContent, outputPath string) error {
	// Clean HTML content from markdown code blocks
	htmlContent = cleanHTMLContent(htmlContent)

	// Create context
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	// Create allocator context
	allocCtx, cancel := chromedp.NewExecAllocator(ctx,
		append(chromedp.DefaultExecAllocatorOptions[:],
			chromedp.Flag("headless", true),
			chromedp.Flag("disable-gpu", true),
			chromedp.Flag("no-sandbox", true),
		)...)
	defer cancel()

	// Create browser context
	browserCtx, cancel := chromedp.NewContext(allocCtx)
	defer cancel()

	// Generate PDF
	var pdfBuf []byte
	if err := chromedp.Run(browserCtx,
		chromedp.Navigate("about:blank"),
		chromedp.ActionFunc(func(ctx context.Context) error {
			// Set the HTML content
			return chromedp.Run(ctx, chromedp.Evaluate(
				fmt.Sprintf(`document.write(%q)`, htmlContent),
				nil,
			))
		}),
		chromedp.ActionFunc(func(ctx context.Context) error {
			// Print to PDF with proper margins
			var err error
			pdfBuf, _, err = page.PrintToPDF().
				WithPaperWidth(8.27).    // A4 width in inches
				WithPaperHeight(11.69).  // A4 height in inches
				WithMarginTop(0.4).
				WithMarginBottom(0.4).
				WithMarginLeft(0.4).
				WithMarginRight(0.4).
				WithPrintBackground(true).
				Do(ctx)
			return err
		}),
	); err != nil {
		return fmt.Errorf("failed to generate PDF: %w", err)
	}

	// Write PDF to file
	if err := os.WriteFile(outputPath, pdfBuf, 0644); err != nil {
		return fmt.Errorf("failed to write PDF file: %w", err)
	}

	return nil
}

// GenerateTempHTMLReportPDF generates a temporary PDF from HTML content
func GenerateTempHTMLReportPDF(clusterName, htmlContent string) (string, error) {
	tempFile, err := os.CreateTemp("", "k8s-report-*.pdf")
	if err != nil {
		return "", fmt.Errorf("failed to create temp file: %w", err)
	}
	tempFile.Close()

	if err := GenerateHTMLReportPDF(clusterName, htmlContent, tempFile.Name()); err != nil {
		os.Remove(tempFile.Name())
		return "", err
	}

	return tempFile.Name(), nil
}

// cleanHTMLContent removes markdown code block markers from HTML content
func cleanHTMLContent(content string) string {
	// Remove ```html at the beginning
	if len(content) > 7 && content[:7] == "```html" {
		content = content[7:]
	}

	// Remove ``` at the end
	if len(content) > 3 && content[len(content)-3:] == "```" {
		content = content[:len(content)-3]
	}

	// Trim whitespace
	content = content[:]
	for len(content) > 0 && (content[0] == '\n' || content[0] == '\r' || content[0] == ' ') {
		content = content[1:]
	}
	for len(content) > 0 && (content[len(content)-1] == '\n' || content[len(content)-1] == '\r' || content[len(content)-1] == ' ') {
		content = content[:len(content)-1]
	}

	return content
}
