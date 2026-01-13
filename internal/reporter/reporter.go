package reporter

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
)

type Reporter struct {
	webhookURL string
	channel    string
	botToken   string
}

func New(webhookURL, channel string) *Reporter {
	return &Reporter{
		webhookURL: webhookURL,
		channel:    channel,
		botToken:   os.Getenv("SLACK_BOT_TOKEN"),
	}
}

func (r *Reporter) SendReport(clusterName, analysis string) error {
	message := formatSlackMessage(clusterName, analysis)

	payload, err := json.Marshal(message)
	if err != nil {
		return fmt.Errorf("failed to marshal slack message: %w", err)
	}

	log.Printf("Sending payload of size: %d bytes", len(payload))

	resp, err := http.Post(r.webhookURL, "application/json", bytes.NewBuffer(payload))
	if err != nil {
		return fmt.Errorf("failed to send slack message: %w", err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)

	if resp.StatusCode != http.StatusOK {
		log.Printf("Slack API error response: %s", string(body))
		return fmt.Errorf("slack API returned status code %d: %s", resp.StatusCode, string(body))
	}

	return nil
}

func (r *Reporter) SendReportWithPDF(clusterName, pdfPath string) error {
	if r.botToken == "" {
		return fmt.Errorf("SLACK_BOT_TOKEN is required to upload files")
	}

	return r.uploadFile(pdfPath, fmt.Sprintf("k8s-health-report-%s.pdf", clusterName))
}

func (r *Reporter) uploadFile(filePath, filename string) error {
	file, err := os.Open(filePath)
	if err != nil {
		return fmt.Errorf("failed to open PDF file: %w", err)
	}
	defer file.Close()

	fileInfo, err := file.Stat()
	if err != nil {
		return fmt.Errorf("failed to stat file: %w", err)
	}

	// Step 1: Get upload URL
	uploadURL, fileID, err := r.getUploadURL(filename, int(fileInfo.Size()))
	if err != nil {
		return fmt.Errorf("failed to get upload URL: %w", err)
	}

	// Step 2: Upload file content
	if err := r.uploadFileContent(uploadURL, file); err != nil {
		return fmt.Errorf("failed to upload file content: %w", err)
	}

	// Step 3: Complete upload
	if err := r.completeUpload(fileID, filename); err != nil {
		return fmt.Errorf("failed to complete upload: %w", err)
	}

	return nil
}

func (r *Reporter) getUploadURL(filename string, fileSize int) (string, string, error) {
	payload := fmt.Sprintf("filename=%s&length=%d", filename, fileSize)

	req, err := http.NewRequest("POST", "https://slack.com/api/files.getUploadURLExternal", bytes.NewBufferString(payload))
	if err != nil {
		return "", "", fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Authorization", "Bearer "+r.botToken)

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return "", "", fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", "", fmt.Errorf("failed to decode response: %w", err)
	}

	if !result["ok"].(bool) {
		return "", "", fmt.Errorf("slack API error: %v", result["error"])
	}

	uploadURL := result["upload_url"].(string)
	fileID := result["file_id"].(string)

	return uploadURL, fileID, nil
}

func (r *Reporter) uploadFileContent(uploadURL string, file *os.File) error {
	req, err := http.NewRequest("POST", uploadURL, file)
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/octet-stream")

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("failed to upload: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("upload failed with status %d: %s", resp.StatusCode, string(body))
	}

	return nil
}

func (r *Reporter) completeUpload(fileID, filename string) error {
	filesJSON := fmt.Sprintf(`[{"title":"K8s Health Report", "id":"%s"}]`, fileID)
	payload := fmt.Sprintf("files=%s&channel_id=%s&initial_comment=Weekly Kubernetes Health Report", filesJSON, r.channel)

	req, err := http.NewRequest("POST", "https://slack.com/api/files.completeUploadExternal", bytes.NewBufferString(payload))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Authorization", "Bearer "+r.botToken)

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	respBody, _ := io.ReadAll(resp.Body)
	log.Printf("Slack complete upload response: %s", string(respBody))

	var result map[string]interface{}
	if err := json.Unmarshal(respBody, &result); err != nil {
		return fmt.Errorf("failed to decode response: %w", err)
	}

	if !result["ok"].(bool) {
		return fmt.Errorf("slack API error: %v", result["error"])
	}

	return nil
}
