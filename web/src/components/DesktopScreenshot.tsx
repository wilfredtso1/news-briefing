import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import Img from './Img.tsx'


    
// Component

        function DesktopScreenshot({
            hasHighlightBorder,
            maxWidth,
            maxHeight,
            imgId
        }: {
            hasHighlightBorder?: boolean;
            maxWidth: string;
            maxHeight: string;
            imgId: string;
        }) {
            return (
                <button className={"marketplaceScreenshots_singleDesktopScreenshot__ns3Pk"}>
                    <div
                        className={
                            hasHighlightBorder
                                ? "roundedMedia_roundedMedia__3rMbX roundedMedia_highlightBorder__cc1XE"
                                : "roundedMedia_roundedMedia__3rMbX"
                        }
                        style={{
                            "--rounded-media-border-radius": "var(--border-radius-400)",
                            "--rounded-media-shadow": "var(--shadow-level-100)",
                            maxWidth: maxWidth,
                            maxHeight: maxHeight
                        } as React.CSSProperties}
                    >
                        <div className={"animation--running"}>
                            <div>
                                <Img id={imgId} />
                            </div>
                        </div>
                    </div>
                </button>
            );
        }
    

export default DesktopScreenshot
