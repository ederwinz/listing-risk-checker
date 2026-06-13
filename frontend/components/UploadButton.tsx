"use client";

import { useRef } from "react";
import { CameraIcon } from "./icons";

interface UploadButtonProps {
  onFiles: (files: File[]) => void;
}

export function UploadButton({ onFiles }: UploadButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length > 0) onFiles(files);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        multiple
        className="hidden"
        style={{ display: "none" }}
        onChange={handleChange}
      />
      <button className="btn btn-primary" onClick={() => inputRef.current?.click()}>
        <CameraIcon /> Check a listing
      </button>
    </>
  );
}
