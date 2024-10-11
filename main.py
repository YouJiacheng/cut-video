from pathlib import Path

import av


def main():
    video_path = Path(r"")
    begin = 0.0  # in seconds
    end = float("inf")  # in seconds
    output_path = Path("cut_video.mp4")

    input_container = av.open(str(video_path))
    output_container = av.open(str(output_path), "w")

    (in_vstream,) = input_container.streams.video
    out_vstream = output_container.add_stream(template=in_vstream)

    # seek to the previous keyframe nearsest to the begin
    # all packets before this keyframe can be safely skipped to reduce the output size
    # av.time_base is actually the reciprocal of the time base
    # ≈ input_container.seek(int(begin / input_video_stream.time_base), backward=True, stream=input_video_stream)
    input_container.seek(int(begin * av.time_base), backward=True)
    # NOTE: seeking offset is based on pts

    prev_keyframe_packet = next(input_container.demux([in_vstream]))
    assert prev_keyframe_packet.stream.type == "video"
    assert prev_keyframe_packet.is_keyframe
    assert prev_keyframe_packet.pts is not None
    video_begin_ts = prev_keyframe_packet.pts
    # next() on input_container.demux() will change the internal state of the input container
    # so we need to seek again
    input_container.seek(video_begin_ts, backward=True, stream=in_vstream)

    match in_astream_tuple := input_container.streams.audio:
        case (s,):
            out_astream = output_container.add_stream(template=s)
            audio_begin_ts = int(video_begin_ts * in_vstream.time_base / s.time_base)
        case ():
            out_astream = None
            audio_begin_ts = 0
        case _:
            raise ValueError("No audio stream found")
    packets = input_container.demux([in_vstream, *in_astream_tuple])

    for packet in packets:
        # skip the "flushing" packets that `demux` generates
        if packet.dts is None:
            continue

        # http://dranger.com/ffmpeg/tutorial05.html
        assert packet.pts is None or packet.dts <= packet.pts

        # we can skip packets decoded after the end
        if packet.dts * packet.time_base > end:
            continue
        # we can't skip packets before the begin
        # because we need all packets starting from the previous keyframe

        match packet.stream.type:
            case "video":
                output_stream = out_vstream
                begin_ts = video_begin_ts
            case "audio":
                assert out_astream is not None
                output_stream = out_astream
                begin_ts = audio_begin_ts
            case _:
                assert False

        packet.stream = output_stream
        packet.dts = packet.dts - begin_ts
        match packet.pts:
            case int(t) if t < begin_ts or t * packet.time_base > end:
                packet.pts = None
            case int(t):
                packet.pts = t - begin_ts
            case None:
                pass

        output_container.mux(packet)

    input_container.close()
    output_container.close()


if __name__ == "__main__":
    main()
