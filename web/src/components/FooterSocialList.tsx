import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import X_logo from './icons/X_logo.tsx'
import Linkedin_logo from './icons/Linkedin_logo.tsx'
import Social_media_facebook_logo from './icons/Social_media_facebook_logo.tsx'
import Instagram_logo from './icons/Instagram_logo.tsx'
import X_logo2 from './icons/X_logo2.tsx'
import Linkedin_logo2 from './icons/Linkedin_logo2.tsx'
import Social_media_facebook_logo1 from './icons/Social_media_facebook_logo1.tsx'
import Media_play_button_rounded from './icons/Media_play_button_rounded.tsx'
import SocialButton from './SocialButton.tsx'
import Footer from './Footer.tsx'


// Component

        function FooterSocialList() {
            return (
                <ul role={"list"} className={"footerSocial_socialList__h7Bi4"}>
                    <FooterSocialItem
                        className={"footerSocial_socialListItem__wdDDq footerSocial_instagram__RqMRr"}
                        icon={<Instagram_logo />}
                    />
                    <FooterSocialItem
                        className={"footerSocial_socialListItem__wdDDq footerSocial_twitter__Ihb5e"}
                        icon={<X_logo2 />}
                    />
                    <FooterSocialItem
                        className={"footerSocial_socialListItem__wdDDq footerSocial_linkedIn__3_fRQ"}
                        icon={<Linkedin_logo2 />}
                    />
                    <FooterSocialItem
                        className={"footerSocial_socialListItem__wdDDq footerSocial_facebook__4ydhX"}
                        icon={<Social_media_facebook_logo1 />}
                    />
                    <FooterSocialItem
                        className={"footerSocial_socialListItem__wdDDq footerSocial_youtube__fuRqz"}
                        icon={<Media_play_button_rounded />}
                    />
                </ul>
            );
        }
    

// Subcomponents

        function FooterSocialItem({ className, icon }: { className: string; icon: JSX.Element }) {
            return (
                <li className={className}>
                    <SocialButton icon={icon} />
                </li>
            );
        }
    

export default FooterSocialList
