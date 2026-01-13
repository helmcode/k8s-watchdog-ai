# Build stage
FROM golang:1.22-alpine AS builder

WORKDIR /build

# Install build dependencies
RUN apk add --no-cache gcc musl-dev sqlite-dev

# Copy go mod files
COPY go.mod go.sum ./
RUN go mod download

# Copy source code
COPY . .

# Build the application
RUN CGO_ENABLED=1 GOOS=linux go build -a -installsuffix cgo -o observer ./cmd/observer

# Runtime stage
FROM alpine:latest

# Install runtime dependencies
RUN apk add --no-cache ca-certificates sqlite-libs tzdata

WORKDIR /app

# Copy binary from builder
COPY --from=builder /build/observer .

# Create data directory
RUN mkdir -p /data && chmod 755 /data

# Run as non-root user
RUN addgroup -g 1000 observer && \
    adduser -D -u 1000 -G observer observer && \
    chown -R observer:observer /app /data

USER observer

ENTRYPOINT ["/app/observer"]
