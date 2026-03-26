import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import Img from './Img.tsx'
import MarketplaceScreenshots from './MarketplaceScreenshots.tsx'


// Component

        function TemplateScreenshotsTest() {
            return (
                <section className={"template_templateScreenshotsTest__Uq8Z8"}>
                    <div>
                        <div
                            className={"roundedMedia_roundedMedia__3rMbX"}
                            style={{
                                "--rounded-media-border-radius": "var(--border-radius-400)",
                                "--rounded-media-shadow": "var(--shadow-level-300)",
                                maxWidth: "1920px",
                                maxHeight: "1200px"
                            } as React.CSSProperties}
                        >
                            <div className={"animation--running"}>
                                <div>
                                    <Img id="1" />
                                </div>
                            </div>
                        </div>
                        <div
                            className={"Spacer_spacer__Hz1_q"}
                            style={{ minHeight: "24px" }}
                        >
                        </div>
                        <div className={"marketplaceScreenshots_desktopScreenshotsContainer__5BZRx"}>
                            <MarketplaceScreenshots />
                        </div>
                    </div>
                </section>
            );
        }
    

export default TemplateScreenshotsTest
