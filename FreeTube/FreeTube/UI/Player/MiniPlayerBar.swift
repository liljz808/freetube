import SwiftUI
import UIKit

/// Public-API mini player sharing the existing playback state and full-screen surface.
@available(iOS 17.0, *)
struct MiniPlayerBar: View {
    @Environment(PlayerStateManager.self) private var player
    let thumbnail: UIImage?

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Button {
                    player.fullScreenPresented = true
                } label: {
                    HStack(spacing: 12) {
                        artwork
                            .frame(width: 48, height: 48)
                            .clipped()
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                        VStack(alignment: .leading, spacing: 3) {
                            Text(verbatim: player.currentVideo?.title ?? "")
                                .font(.subheadline.weight(.semibold))
                                .lineLimit(1)
                            subtitle
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .contentShape(Rectangle())
                }
                .accessibilityLabel("Open full screen player")
                .accessibilityIdentifier("miniPlayer.open")

                Button {
                    player.togglePlayPause()
                } label: {
                    Image(systemName: player.isPlaying ? "pause.fill" : "play.fill")
                        .frame(width: 44, height: 44)
                }
                .accessibilityLabel(player.isPlaying ? Text("Pause") : Text("Play"))
                .accessibilityIdentifier("miniPlayer.playPause")

                Button {
                    player.playNext()
                } label: {
                    Image(systemName: "forward.fill")
                        .frame(width: 44, height: 44)
                }
                .accessibilityLabel("Next video")
                .accessibilityIdentifier("miniPlayer.next")
            }
            .padding(8)

            ProgressView(value: progress)
                .progressViewStyle(.linear)
                .accessibilityLabel("Playback or download progress")
        }
        .buttonStyle(.plain)
        .foregroundStyle(.primary)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .simultaneousGesture(
            DragGesture(minimumDistance: 30)
                .onEnded { value in
                    if value.translation.height < -50,
                       abs(value.translation.width) < abs(value.translation.height) {
                        player.fullScreenPresented = true
                    }
                }
        )
    }

    @ViewBuilder
    private var artwork: some View {
        switch player.loadState {
        case .resolving, .downloading:
            Image(systemName: "arrow.down.circle.fill")
                .font(.title)
        default:
            if let thumbnail {
                Image(uiImage: thumbnail).resizable().scaledToFill()
            } else {
                Image(systemName: "play.rectangle.fill").font(.title)
            }
        }
    }

    @ViewBuilder
    private var subtitle: some View {
        switch player.loadState {
        case .resolving:
            Text("Preparing…")
        case .downloading(let value, _):
            if let value, value.isFinite {
                Text("Downloading \(Int(min(1, max(0, value)) * 100))%")
            } else {
                Text("Processing…")
            }
        case .failed(let message):
            Text(verbatim: message)
        case .idle, .readyToPlay:
            Text(verbatim: player.currentVideo?.channelName ?? "")
        }
    }

    private var progress: Double {
        if case .downloading(let value, _) = player.loadState {
            return normalized(value ?? 0)
        }
        guard player.duration > 0 else { return 0 }
        return normalized(player.elapsed / player.duration)
    }

    private func normalized(_ value: Double) -> Double {
        value.isFinite ? min(1, max(0, value)) : 0
    }
}
